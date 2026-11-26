"""StegoShield Cryptographic Engine (Module A), format v2.

Authenticated encryption for the two keying modes:
- Password mode:   PBKDF2-HMAC-SHA256 (600,000 iterations) + HKDF + AES-256-GCM.
- Asymmetric mode: X25519 ECDH with a one-time sender key + HKDF + AES-256-GCM.

Design rule for v2: every byte that ends up inside the image must look random.
The packet therefore carries NO magic bytes, version or mode in the clear. These
are bound into the AES-GCM Additional Authenticated Data (AAD) instead, so they
are still verified but never embedded. The length field is masked with a
key-derived value.

Packet layout (what gets embedded):

    stage 1 : kdf_material   16 B salt (password) | 32 B one-time X25519 public key
    stage 2 : nonce (12 B) || masked_length (4 B) || ciphertext + GCM tag (len + 16 B)

Stage 1 is placed at positions derived from a cheap *locator key* (password or
recipient public key). That is safe because stage 1 is random data, so finding
it reveals nothing. Stage 2 is placed at positions derived from the *slot key*,
which only exists after the expensive PBKDF2 or the ECDH exchange.
See docs/payload_format.md.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ==============================================================================
# Protocol constants
# ==============================================================================

MAGIC: bytes = b"STSH"  # authenticated via AAD only, never embedded
VERSION: int = 2
MODE_PASSWORD: int = 1
MODE_ASYMMETRIC: int = 2

SALT_SIZE: int = 16
NONCE_SIZE: int = 12
LENGTH_SIZE: int = 4
TAG_SIZE: int = 16
X25519_KEY_SIZE: int = 32
PBKDF2_ITERATIONS: int = 600_000

# Bytes stored in stage 1 for each mode
STAGE1_SIZE: dict[int, int] = {MODE_PASSWORD: SALT_SIZE, MODE_ASYMMETRIC: X25519_KEY_SIZE}
# Fixed-size prefix of stage 2 (nonce + masked length)
STAGE2_HEADER_SIZE: int = NONCE_SIZE + LENGTH_SIZE


def packet_overhead(mode: int) -> int:
    """Bytes added on top of the plaintext: stage 1 + nonce + length + tag."""
    return STAGE1_SIZE[mode] + STAGE2_HEADER_SIZE + TAG_SIZE


# ==============================================================================
# Errors
# ==============================================================================


class StegoCryptoError(Exception):
    """Base exception for cryptographic operations in StegoShield."""


class AuthenticationError(StegoCryptoError):
    """Wrong key, no message present, or data was modified.

    These cases are deliberately indistinguishable: telling them apart would
    let an attacker confirm whether an image carries a message.
    """


class InvalidPayloadError(StegoCryptoError):
    """The packet is structurally impossible (e.g. too short to parse)."""


NO_MESSAGE_TEXT = (
    "No hidden message could be recovered with this key. "
    "The key is wrong, the image holds no message, or the image was modified."
)


# ==============================================================================
# Key derivation
# ==============================================================================


@dataclass(frozen=True)
class SessionKeys:
    """Independent sub-keys derived from one master secret (HKDF domain separation)."""

    enc_key: bytes  # AES-256-GCM key
    slot_key: bytes  # seeds the stage-2 pixel positions
    mask_key: bytes  # masks the length field
    matching_key: bytes  # seeds the +/-1 choices of LSB matching


def _hkdf(ikm: bytes, info: bytes, salt: bytes | None = None, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _session_from_master(master: bytes) -> SessionKeys:
    return SessionKeys(
        enc_key=_hkdf(master, b"stegoshield-v2-aes-key"),
        slot_key=_hkdf(master, b"stegoshield-v2-slot-key"),
        mask_key=_hkdf(master, b"stegoshield-v2-length-mask", length=LENGTH_SIZE),
        matching_key=_hkdf(master, b"stegoshield-v2-matching-seed"),
    )


def _raw_public(pub: x25519.X25519PublicKey) -> bytes:
    return pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)


def locator_key_from_password(password: str) -> bytes:
    """Cheap key that only locates stage 1 (the random salt).

    Being cheap is fine: an attacker who guesses the password and reads stage 1
    gets 16 random bytes, which can't confirm or reject the guess.
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    return _hkdf(password.encode("utf-8"), b"stegoshield-v2-locator-password", salt=b"stegoshield-v2-locator")


def locator_key_from_public_key(public_key: x25519.X25519PublicKey) -> bytes:
    """Key that locates stage 1 (the one-time sender public key) from the recipient's public key."""
    return _hkdf(_raw_public(public_key), b"stegoshield-v2-locator-x25519", salt=b"stegoshield-v2-locator")


def derive_password_session(password: str, salt: bytes) -> SessionKeys:
    """PBKDF2-HMAC-SHA256 (600k iterations) then HKDF into independent sub-keys."""
    if not password:
        raise ValueError("Password cannot be empty.")
    master = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS).derive(
        password.encode("utf-8")
    )
    return _session_from_master(master)


def _canonical_x25519(embedded: bytes) -> bytes:
    """Clear the top bit. X25519 ignores it (RFC 7748), and we randomise it when embedding."""
    return embedded[:-1] + bytes([embedded[-1] & 0x7F])


def _asymmetric_master(shared_secret: bytes, eph_canonical: bytes, recipient_raw: bytes) -> bytes:
    return _hkdf(shared_secret, b"stegoshield-v2-x25519-master", salt=eph_canonical + recipient_raw)


def new_asymmetric_session(
    recipient_public_key: x25519.X25519PublicKey,
) -> tuple[bytes, SessionKeys]:
    """Sender side: make a one-time keypair, run ECDH, derive sub-keys.

    Returns the 32 bytes to embed in stage 1 (one-time public key with a random
    top bit, so it has no constant bit) and the session keys.
    """
    if not isinstance(recipient_public_key, x25519.X25519PublicKey):
        raise TypeError("recipient_public_key must be an X25519PublicKey.")
    eph_priv = x25519.X25519PrivateKey.generate()
    eph_canonical = _raw_public(eph_priv.public_key())
    top_bit = os.urandom(1)[0] & 0x80
    eph_embedded = eph_canonical[:-1] + bytes([eph_canonical[-1] | top_bit])

    shared = eph_priv.exchange(recipient_public_key)
    master = _asymmetric_master(shared, eph_canonical, _raw_public(recipient_public_key))
    return eph_embedded, _session_from_master(master)


def open_asymmetric_session(
    recipient_private_key: x25519.X25519PrivateKey,
    eph_embedded: bytes,
) -> SessionKeys:
    """Recipient side: recompute the session keys from the embedded one-time public key."""
    if not isinstance(recipient_private_key, x25519.X25519PrivateKey):
        raise TypeError("recipient_private_key must be an X25519PrivateKey.")
    if len(eph_embedded) != X25519_KEY_SIZE:
        raise InvalidPayloadError("One-time public key has the wrong length.")
    eph_canonical = _canonical_x25519(eph_embedded)
    try:
        shared = recipient_private_key.exchange(x25519.X25519PublicKey.from_public_bytes(eph_canonical))
    except ValueError as e:  # all-zero shared secret (low-order point): treat as no message
        raise AuthenticationError(NO_MESSAGE_TEXT) from e
    master = _asymmetric_master(shared, eph_canonical, _raw_public(recipient_private_key.public_key()))
    return _session_from_master(master)


# ==============================================================================
# Sealing / opening stage 2
# ==============================================================================


def _aad(mode: int, stage1: bytes, nonce: bytes, length: int) -> bytes:
    """Everything that must be authenticated but not embedded."""
    return MAGIC + bytes([VERSION, mode]) + stage1 + nonce + struct.pack(">I", length)


def _mask(length: int, mask_key: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(struct.pack(">I", length), mask_key, strict=True))


def unmask_length(masked: bytes, keys: SessionKeys) -> int:
    """Recover the ciphertext length from its masked 4-byte form."""
    (length,) = struct.unpack(">I", bytes(a ^ b for a, b in zip(masked, keys.mask_key, strict=True)))
    return length


def seal(mode: int, stage1: bytes, keys: SessionKeys, plaintext: bytes | str) -> bytes:
    """Encrypt plaintext and return stage 2: nonce || masked_length || ciphertext+tag."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    if not plaintext:
        raise ValueError("Plaintext cannot be empty.")
    nonce = os.urandom(NONCE_SIZE)
    length = len(plaintext) + TAG_SIZE
    ct = AESGCM(keys.enc_key).encrypt(nonce, plaintext, _aad(mode, stage1, nonce, length))
    return nonce + _mask(length, keys.mask_key) + ct


def open_sealed(mode: int, stage1: bytes, keys: SessionKeys, stage2: bytes) -> bytes:
    """Verify and decrypt stage 2. Raises AuthenticationError on any mismatch."""
    if len(stage2) < STAGE2_HEADER_SIZE + TAG_SIZE:
        raise InvalidPayloadError("Packet is too short to contain a message.")
    nonce = stage2[:NONCE_SIZE]
    length = unmask_length(stage2[NONCE_SIZE:STAGE2_HEADER_SIZE], keys)
    ct = stage2[STAGE2_HEADER_SIZE:]
    if length != len(ct):
        raise AuthenticationError(NO_MESSAGE_TEXT)
    try:
        return AESGCM(keys.enc_key).decrypt(nonce, ct, _aad(mode, stage1, nonce, length))
    except InvalidTag as e:
        raise AuthenticationError(NO_MESSAGE_TEXT) from e


# ==============================================================================
# Whole-packet helpers (packet = stage1 || stage2)
# ==============================================================================


def encrypt_password(plaintext: bytes | str, password: str) -> bytes:
    """Encrypt with a password. Returns the full packet: salt || stage 2."""
    salt = os.urandom(SALT_SIZE)
    keys = derive_password_session(password, salt)
    return salt + seal(MODE_PASSWORD, salt, keys, plaintext)


def decrypt_password(packet: bytes, password: str) -> bytes:
    """Decrypt a full password-mode packet."""
    if not password:
        raise ValueError("Password cannot be empty.")
    if len(packet) < packet_overhead(MODE_PASSWORD):
        raise InvalidPayloadError("Packet is too short to contain a message.")
    salt, stage2 = packet[:SALT_SIZE], packet[SALT_SIZE:]
    return open_sealed(MODE_PASSWORD, salt, derive_password_session(password, salt), stage2)


def encrypt_asymmetric(plaintext: bytes | str, recipient_public_key: x25519.X25519PublicKey) -> bytes:
    """Encrypt to a recipient's public key. Returns the full packet: one-time pubkey || stage 2."""
    eph, keys = new_asymmetric_session(recipient_public_key)
    return eph + seal(MODE_ASYMMETRIC, eph, keys, plaintext)


def decrypt_asymmetric(packet: bytes, recipient_private_key: x25519.X25519PrivateKey) -> bytes:
    """Decrypt a full asymmetric-mode packet with the recipient's private key."""
    if len(packet) < packet_overhead(MODE_ASYMMETRIC):
        raise InvalidPayloadError("Packet is too short to contain a message.")
    eph, stage2 = packet[:X25519_KEY_SIZE], packet[X25519_KEY_SIZE:]
    keys = open_asymmetric_session(recipient_private_key, eph)
    return open_sealed(MODE_ASYMMETRIC, eph, keys, stage2)
