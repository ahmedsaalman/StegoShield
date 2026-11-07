"""StegoShield End-to-End Pipeline & CLI (Task L15).

Unifies:
  Encrypt -> Keyed Permutation Embed -> Lossless PNG Generation
  Load PNG -> Keyed Permutation Extract -> Authenticated Decryption
Supports both password-based symmetric mode and X25519 asymmetric mode.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Union
from PIL import Image

from cryptography.hazmat.primitives.asymmetric import x25519

from core.crypto import (
    encrypt_password,
    decrypt_password,
    encrypt_asymmetric,
    decrypt_asymmetric,
    derive_permutation_key_from_password,
    derive_permutation_key_from_public_key,
)
from core.keys import (
    generate_keypair,
    export_private_key_pem,
    import_private_key_pem,
    export_public_key_pem,
    import_public_key_auto,
)
from core.embed import embed_payload, extract_payload, EmbeddingAlgorithm, EmbeddingMode
from core.capacity import calculate_image_capacity, check_capacity


def _load_image(img_input: Union[str, Path, Image.Image]) -> Image.Image:
    if isinstance(img_input, (str, Path)):
        return Image.open(str(img_input))
    elif isinstance(img_input, Image.Image):
        return img_input
    raise TypeError(f"Expected file path or PIL Image, got {type(img_input).__name__}")


# ==============================================================================
# Password-Based High-Level Pipeline
# ==============================================================================

def stego_encode_password(
    cover: Union[str, Path, Image.Image],
    secret_message: Union[str, bytes],
    password: str,
    algorithm: EmbeddingAlgorithm = "replacement",
    mode: EmbeddingMode = "pseudorandom",
) -> Image.Image:
    """Encrypt and embed secret message into cover image using password mode."""
    cover_img = _load_image(cover)
    payload_bytes, perm_key = encrypt_password(secret_message, password)

    effective_perm_key = perm_key if mode == "pseudorandom" else None
    return embed_payload(
        cover_image=cover_img,
        payload_bytes=payload_bytes,
        perm_key=effective_perm_key,
        mode=mode,
        algorithm=algorithm,
    )


def stego_decode_password(
    stego: Union[str, Path, Image.Image],
    password: str,
    mode: EmbeddingMode = "pseudorandom",
) -> bytes:
    """Extract and decrypt secret message from stego image using password mode."""
    stego_img = _load_image(stego)
    effective_perm_key = derive_permutation_key_from_password(password) if mode == "pseudorandom" else None

    payload_bytes = extract_payload(
        stego_image=stego_img,
        perm_key=effective_perm_key,
        mode=mode,
    )
    return decrypt_password(payload_bytes, password)


# ==============================================================================
# Asymmetric (X25519) High-Level Pipeline
# ==============================================================================

def stego_encode_asymmetric(
    cover: Union[str, Path, Image.Image],
    secret_message: Union[str, bytes],
    recipient_public_key: x25519.X25519PublicKey,
    algorithm: EmbeddingAlgorithm = "replacement",
    mode: EmbeddingMode = "pseudorandom",
) -> Image.Image:
    """Encrypt and embed secret message into cover image using recipient's public key."""
    cover_img = _load_image(cover)
    payload_bytes, perm_key = encrypt_asymmetric(secret_message, recipient_public_key)

    effective_perm_key = perm_key if mode == "pseudorandom" else None
    return embed_payload(
        cover_image=cover_img,
        payload_bytes=payload_bytes,
        perm_key=effective_perm_key,
        mode=mode,
        algorithm=algorithm,
    )


def stego_decode_asymmetric(
    stego: Union[str, Path, Image.Image],
    recipient_private_key: x25519.X25519PrivateKey,
    mode: EmbeddingMode = "pseudorandom",
) -> bytes:
    """Extract and decrypt secret message from stego image using recipient's private key."""
    stego_img = _load_image(stego)
    pub = recipient_private_key.public_key()
    effective_perm_key = derive_permutation_key_from_public_key(pub) if mode == "pseudorandom" else None

    payload_bytes = extract_payload(
        stego_image=stego_img,
        perm_key=effective_perm_key,
        mode=mode,
    )
    return decrypt_asymmetric(payload_bytes, recipient_private_key)


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
        print(f"[+] Keypair generated successfully.")
        print(f"    Private key saved to: {args.out_priv}")
        print(f"    Public key saved to:  {args.out_pub}")

    elif args.command == "capacity":
        img = Image.open(args.cover)
        cap = calculate_image_capacity(img)
        print(f"Cover Image Capacity ({cap['width']}x{cap['height']}, {cap['channels']} channels):")
        print(f"  Total carrier slots:  {cap['total_carrier_bits']} bits")
        print(f"  Maximum payload:      {cap['max_payload_bytes']:,} bytes")
        print(f"  Safe payload (10%):   {cap['safe_payload_bytes']:,} bytes")
        print(f"  Moderate payload (25%): {cap['moderate_payload_bytes']:,} bytes")

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

