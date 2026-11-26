"""StegoShield End-to-End Pipeline & CLI (format v2).

Hide:    encrypt -> stage 1 at locator-key slots -> stage 2 at slot-key slots -> PNG
Reveal:  read stage 1 -> derive keys (PBKDF2 / ECDH) -> read stage 2 -> verify & decrypt

Stage 1 holds only random bytes (salt or one-time public key), so the cheap
locator key reveals nothing. Stage 2 positions need the derived secret, so they
can't be found without the password or private key. See docs/payload_format.md.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives.asymmetric import x25519
from PIL import Image

from core.capacity import CapacityExceededError, calculate_image_capacity
from core.crypto import (
    MODE_ASYMMETRIC,
    MODE_PASSWORD,
    NO_MESSAGE_TEXT,
    NONCE_SIZE,
    SALT_SIZE,
    STAGE1_SIZE,
    STAGE2_HEADER_SIZE,
    TAG_SIZE,
    AuthenticationError,
    SessionKeys,
    derive_password_session,
    locator_key_from_password,
    locator_key_from_public_key,
    new_asymmetric_session,
    open_asymmetric_session,
    open_sealed,
    packet_overhead,
    seal,
    unmask_length,
)
from core.embed import (
    EmbeddingAlgorithm,
    EmbeddingMode,
    bits_to_bytes,
    bytes_to_bits,
    carrier_to_image,
    image_to_carrier,
    read_bits,
    select_slots,
    write_bits,
)
from core.keys import (
    export_private_key_pem,
    export_public_key_pem,
    generate_keypair,
    import_private_key_pem,
    import_public_key_auto,
)

ImageInput = str | Path | Image.Image


def _load_image(img_input: ImageInput) -> Image.Image:
    if isinstance(img_input, (str, Path)):
        return Image.open(str(img_input))
    if isinstance(img_input, Image.Image):
        return img_input
    raise TypeError(f"Expected file path or PIL Image, got {type(img_input).__name__}")


def max_message_bytes(image: Image.Image, enc_mode: str = "password") -> int:
    """Largest plaintext (in bytes) this image can carry in the given mode."""
    mode_id = MODE_PASSWORD if enc_mode == "password" else MODE_ASYMMETRIC
    slots = calculate_image_capacity(image)["total_carrier_bits"]
    return max(0, slots // 8 - packet_overhead(mode_id))


# ==============================================================================
# Two-stage core
# ==============================================================================

def _hide(
    cover: Image.Image,
    locator_key: bytes,
    stage1: bytes,
    keys: SessionKeys,
    stage2: bytes,
    algorithm: EmbeddingAlgorithm,
    mode: EmbeddingMode,
    mode_id: int,
) -> Image.Image:
    arr, flat, img_mode = image_to_carrier(cover)
    total = len(flat)
    need_bits = (len(stage1) + len(stage2)) * 8
    if need_bits > total:
        plaintext_len = len(stage2) - STAGE2_HEADER_SIZE - TAG_SIZE
        raise CapacityExceededError(
            f"Message is {plaintext_len:,} bytes but this {cover.width}x{cover.height} image "
            f"can hold at most {max(0, total // 8 - packet_overhead(mode_id)):,} bytes."
        )
    s1 = select_slots(total, len(stage1) * 8, locator_key, mode)
    s2 = select_slots(total, len(stage2) * 8, keys.slot_key, mode, exclude=s1)
    rng = np.random.default_rng(int.from_bytes(keys.matching_key, "big"))
    write_bits(flat, s1, bytes_to_bits(stage1), algorithm, rng)
    write_bits(flat, s2, bytes_to_bits(stage2), algorithm, rng)
    return carrier_to_image(arr, flat, img_mode)


def _reveal(
    stego: Image.Image,
    locator_key: bytes,
    open_keys: Callable[[bytes], SessionKeys],
    mode: EmbeddingMode,
    mode_id: int,
) -> bytes:
    _, flat, _ = image_to_carrier(stego)
    total = len(flat)
    s1_bits = STAGE1_SIZE[mode_id] * 8
    hdr_bits = STAGE2_HEADER_SIZE * 8
    if total < s1_bits + hdr_bits + TAG_SIZE * 8:
        raise AuthenticationError(NO_MESSAGE_TEXT)

    # Stage 1: random salt / one-time public key
    s1 = select_slots(total, s1_bits, locator_key, mode)
    stage1 = bits_to_bytes(read_bits(flat, s1))
    keys = open_keys(stage1)

    # Stage 2 header: nonce + masked length
    hdr = bits_to_bytes(read_bits(flat, select_slots(total, hdr_bits, keys.slot_key, mode, exclude=s1)))
    length = unmask_length(hdr[NONCE_SIZE:], keys)
    if length <= TAG_SIZE or s1_bits + hdr_bits + length * 8 > total:
        raise AuthenticationError(NO_MESSAGE_TEXT)

    # Full stage 2 (prefix property: the first hdr_bits slots are the header again)
    s2 = select_slots(total, hdr_bits + length * 8, keys.slot_key, mode, exclude=s1)
    stage2 = bits_to_bytes(read_bits(flat, s2))
    return open_sealed(mode_id, stage1, keys, stage2)


# ==============================================================================
# Password mode
# ==============================================================================

def stego_encode_password(
    cover: ImageInput,
    secret_message: str | bytes,
    password: str,
    algorithm: EmbeddingAlgorithm = "replacement",
    mode: EmbeddingMode = "pseudorandom",
) -> Image.Image:
    """Encrypt with a password and hide the message in the cover image."""
    salt = os.urandom(SALT_SIZE)
    keys = derive_password_session(password, salt)
    stage2 = seal(MODE_PASSWORD, salt, keys, secret_message)
    return _hide(
        _load_image(cover), locator_key_from_password(password), salt, keys, stage2,
        algorithm, mode, MODE_PASSWORD,
    )


def stego_decode_password(
    stego: ImageInput,
    password: str,
    mode: EmbeddingMode = "pseudorandom",
) -> bytes:
    """Recover and decrypt a password-mode message."""
    return _reveal(
        _load_image(stego), locator_key_from_password(password),
        lambda salt: derive_password_session(password, salt), mode, MODE_PASSWORD,
    )


# ==============================================================================
# Asymmetric (X25519) mode
# ==============================================================================

def stego_encode_asymmetric(
    cover: ImageInput,
    secret_message: str | bytes,
    recipient_public_key: x25519.X25519PublicKey,
    algorithm: EmbeddingAlgorithm = "replacement",
    mode: EmbeddingMode = "pseudorandom",
) -> Image.Image:
    """Encrypt to the recipient's public key and hide the message in the cover image."""
    eph, keys = new_asymmetric_session(recipient_public_key)
    stage2 = seal(MODE_ASYMMETRIC, eph, keys, secret_message)
    return _hide(
        _load_image(cover), locator_key_from_public_key(recipient_public_key), eph, keys, stage2,
        algorithm, mode, MODE_ASYMMETRIC,
    )


def stego_decode_asymmetric(
    stego: ImageInput,
    recipient_private_key: x25519.X25519PrivateKey,
    mode: EmbeddingMode = "pseudorandom",
) -> bytes:
    """Recover and decrypt an asymmetric-mode message with the recipient's private key."""
    return _reveal(
        _load_image(stego), locator_key_from_public_key(recipient_private_key.public_key()),
        lambda eph: open_asymmetric_session(recipient_private_key, eph), mode, MODE_ASYMMETRIC,
    )


# ==============================================================================
# CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="StegoShield",
        description="StegoShield CLI: Encrypted Steganography & Steganalysis",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: gen-keys
    p_gen = subparsers.add_parser("gen-keys", help="Generate X25519 keypair")
    p_gen.add_argument("--out-priv", default="private_key.pem", help="Path to write private key PEM")
    p_gen.add_argument("--out-pub", default="public_key.pem", help="Path to write public key PEM")
    p_gen.add_argument("--passphrase", default=None, help="Optional passphrase for private key")

    # Subcommand: capacity
    p_cap = subparsers.add_parser("capacity", help="Check carrier capacity")
    p_cap.add_argument("--cover", required=True, help="Cover image path")

    # Subcommand: hide-pass
    p_hide_pass = subparsers.add_parser("hide-pass", help="Encrypt & embed message with password")
    p_hide_pass.add_argument("--cover", required=True, help="Input cover image (PNG/JPG)")
    p_hide_pass.add_argument("--message", required=True, help="Secret text message")
    p_hide_pass.add_argument("--password", required=True, help="Shared password")
    p_hide_pass.add_argument("--out", required=True, help="Output stego PNG path")
    p_hide_pass.add_argument("--algo", choices=["replacement", "matching"], default="replacement")
    p_hide_pass.add_argument("--mode", choices=["pseudorandom", "sequential"], default="pseudorandom")

    # Subcommand: extract-pass
    p_ext_pass = subparsers.add_parser("extract-pass", help="Extract & decrypt message with password")
    p_ext_pass.add_argument("--stego", required=True, help="Input stego PNG image")
    p_ext_pass.add_argument("--password", required=True, help="Shared password")
    p_ext_pass.add_argument("--mode", choices=["pseudorandom", "sequential"], default="pseudorandom")

    # Subcommand: hide-asym
    p_hide_asym = subparsers.add_parser("hide-asym", help="Encrypt & embed with recipient public key")
    p_hide_asym.add_argument("--cover", required=True, help="Input cover image (PNG/JPG)")
    p_hide_asym.add_argument("--message", required=True, help="Secret text message")
    p_hide_asym.add_argument("--pubkey", required=True, help="Recipient public key (file or string)")
    p_hide_asym.add_argument("--out", required=True, help="Output stego PNG path")
    p_hide_asym.add_argument("--algo", choices=["replacement", "matching"], default="replacement")
    p_hide_asym.add_argument("--mode", choices=["pseudorandom", "sequential"], default="pseudorandom")

    # Subcommand: extract-asym
    p_ext_asym = subparsers.add_parser("extract-asym", help="Extract & decrypt with recipient private key")
    p_ext_asym.add_argument("--stego", required=True, help="Input stego PNG image")
    p_ext_asym.add_argument("--privkey", required=True, help="Path to private key PEM file")
    p_ext_asym.add_argument("--passphrase", default=None, help="Passphrase if private key is encrypted")
    p_ext_asym.add_argument("--mode", choices=["pseudorandom", "sequential"], default="pseudorandom")

    args = parser.parse_args()

    if args.command == "gen-keys":
        priv, pub = generate_keypair()
        priv_pem = export_private_key_pem(priv, password=args.passphrase)
        pub_pem = export_public_key_pem(pub)
        Path(args.out_priv).write_text(priv_pem, encoding="utf-8")
        Path(args.out_pub).write_text(pub_pem, encoding="utf-8")
        print("[+] Keypair generated successfully.")
        print(f"    Private key saved to: {args.out_priv}")
        print(f"    Public key saved to:  {args.out_pub}")

    elif args.command == "capacity":
        img = Image.open(args.cover)
        cap = calculate_image_capacity(img)
        print(f"Cover Image Capacity ({cap['width']}x{cap['height']}, {cap['channels']} channels):")
        print(f"  Total carrier slots:  {cap['total_carrier_bits']} bits")
        print(f"  Max message (password mode):   {max_message_bytes(img, 'password'):,} bytes")
        print(f"  Max message (public-key mode): {max_message_bytes(img, 'asymmetric'):,} bytes")

    elif args.command == "hide-pass":
        stego_img = stego_encode_password(
            cover=args.cover,
            secret_message=args.message,
            password=args.password,
            algorithm=args.algo,
            mode=args.mode,
        )
        stego_img.save(args.out, format="PNG")
        print(f"[+] Successfully encrypted and embedded message into: {args.out}")

    elif args.command == "extract-pass":
        secret_bytes = stego_decode_password(
            stego=args.stego,
            password=args.password,
            mode=args.mode,
        )
        print(f"[+] Secret Message: {secret_bytes.decode('utf-8', errors='replace')}")

    elif args.command == "hide-asym":
        key_input = args.pubkey
        if Path(key_input).exists():
            key_input = Path(key_input).read_text(encoding="utf-8")
        pub = import_public_key_auto(key_input)
        stego_img = stego_encode_asymmetric(
            cover=args.cover,
            secret_message=args.message,
            recipient_public_key=pub,
            algorithm=args.algo,
            mode=args.mode,
        )
        stego_img.save(args.out, format="PNG")
        print(f"[+] Successfully encrypted with X25519 ECDH and embedded into: {args.out}")

    elif args.command == "extract-asym":
        pem_text = Path(args.privkey).read_text(encoding="utf-8")
        priv = import_private_key_pem(pem_text, password=args.passphrase)
        secret_bytes = stego_decode_asymmetric(
            stego=args.stego,
            recipient_private_key=priv,
            mode=args.mode,
        )
        print(f"[+] Secret Message: {secret_bytes.decode('utf-8', errors='replace')}")


if __name__ == "__main__":
    main()

