"""StegoShield Cryptographic Engine (Module A).

Implements authenticated symmetric and asymmetric encryption:
- Password mode: PBKDF2-HMAC-SHA256 (600,000 iterations) + AES-256-GCM.
- Asymmetric mode: X25519 ECDH + HKDF-SHA256 + AES-256-GCM with ephemeral sender keys.
- Additional Authenticated Data (AAD) binding on protocol headers to thwart tampering.
- Cryptographically isolated sub-key derivation for pseudorandom pixel permutation.
"""

from __future__ import annotations

import os
import struct
from typing import Tuple, Dict, Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# Protocol Constants
MAGIC: bytes = b"STSH"
VERSION: int = 1
MODE_PASSWORD: int = 1
MODE_ASYMMETRIC: int = 2

SALT_SIZE: int = 16
NONCE_SIZE: int = 12
TAG_SIZE: int = 16
X25519_KEY_SIZE: int = 32
PBKDF2_ITERATIONS: int = 600_000

# Header layout sizes
# Mode 1: Magic(4) + Ver(1) + Mode(1) + Salt(16) + Nonce(12) + Length(4) = 38 bytes
MODE_1_HEADER_SIZE: int = 4 + 1 + 1 + SALT_SIZE + NONCE_SIZE + 4
# Mode 2: Magic(4) + Ver(1) + Mode(1) + EphPub(32) + Nonce(12) + Length(4) = 54 bytes
MODE_2_HEADER_SIZE: int = 4 + 1 + 1 + X25519_KEY_SIZE + NONCE_SIZE + 4


class StegoCryptoError(Exception):
    """Base exception for cryptographic operations in StegoShield."""
    pass


class AuthenticationError(StegoCryptoError):
    """Raised when authentication tag verification fails or data was tampered."""
    pass


class InvalidPayloadError(StegoCryptoError):
    """Raised when payload headers, magic bytes, or versions are invalid."""
    pass


def derive_permutation_key_from_password(password: str) -> bytes:
    """Derive a 32-byte deterministic permutation key from a password.
    
    This solves the receiver permutation discovery problem: anyone possessing the
    password can construct the exact pixel shuffle without needing to parse the
    embedded header first.
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"stegoshield-permutation-salt-v1",
        info=b"stegoshield-password-pixel-permutation",
    )
    return hkdf.derive(password.encode("utf-8"))


def derive_permutation_key_from_public_key(public_key: x25519.X25519PublicKey) -> bytes:
    """Derive a 32-byte deterministic permutation key from recipient's public key."""
    raw_pub = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"stegoshield-permutation-salt-v1",
        info=b"stegoshield-asymmetric-pixel-permutation",
    )
    return hkdf.derive(raw_pub)


def _derive_symmetric_keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    """Derive AES encryption key and payload permutation key using PBKDF2 + HKDF."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    master_key = kdf.derive(password.encode("utf-8"))

    # Derive separate AES encryption key
    enc_kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stegoshield-aes-encryption",
    )
    enc_key = enc_kdf.derive(master_key)

    # Derive separate permutation seed (used when payload-specific permutation is requested)
    perm_kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stegoshield-pixel-permutation",
    )
    perm_key = perm_kdf.derive(master_key)
    return enc_key, perm_key


def _derive_asymmetric_keys(shared_secret: bytes) -> tuple[bytes, bytes]:
    """Derive AES encryption key and permutation key from ECDH shared secret."""
    master_kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stegoshield-x25519-master",
    )
    master_key = master_kdf.derive(shared_secret)

    enc_kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stegoshield-aes-encryption",
    )
    enc_key = enc_kdf.derive(master_key)

    perm_kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stegoshield-pixel-permutation",
    )
    perm_key = perm_kdf.derive(master_key)
    return enc_key, perm_key


def encrypt_password(plaintext: bytes | str, password: str) -> tuple[bytes, bytes]:
    """Encrypt plaintext using PBKDF2-HMAC-SHA256 and AES-256-GCM.
    
    Returns:
        tuple[bytes, bytes]: (full_payload_bytes, permutation_key)
    """
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    if not plaintext:
        raise ValueError("Plaintext cannot be empty.")
    if not password:
        raise ValueError("Password cannot be empty.")

    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    enc_key, _ = _derive_symmetric_keys(password, salt)
    perm_key = derive_permutation_key_from_password(password)

    # Calculate ciphertext length (AES-GCM adds 16-byte tag)
    cipher_len = len(plaintext) + TAG_SIZE

    # Header: Magic(4) + Version(1) + Mode(1) + Salt(16) + Nonce(12) + Length(4)
    header = (
        MAGIC
        + bytes([VERSION, MODE_PASSWORD])
        + salt
        + nonce
        + struct.pack(">I", cipher_len)
    )

    # Pass the entire header as AAD (Additional Authenticated Data)
    aesgcm = AESGCM(enc_key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=header)

    full_payload = header + ciphertext_and_tag
    return full_payload, perm_key


def decrypt_password(payload_bytes: bytes, password: str) -> bytes:
    """Decrypt and authenticate a StegoShield payload using password mode.
    
    Raises:
        InvalidPayloadError: If magic, version, mode, or length is invalid.
        AuthenticationError: If AES-GCM tag verification fails (wrong key or tampering).
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    if len(payload_bytes) < MODE_1_HEADER_SIZE + TAG_SIZE:
        raise InvalidPayloadError("Payload is too short to be a valid StegoShield payload.")

    magic = payload_bytes[:4]
    if magic != MAGIC:
        raise InvalidPayloadError(f"Invalid magic bytes: expected {MAGIC!r}, got {magic!r}")

    version = payload_bytes[4]
    if version != VERSION:
        raise InvalidPayloadError(f"Unsupported protocol version: {version}")

    mode = payload_bytes[5]
    if mode != MODE_PASSWORD:
        raise InvalidPayloadError(f"Expected password mode ({MODE_PASSWORD}), got mode {mode}")

    offset = 6
    salt = payload_bytes[offset : offset + SALT_SIZE]
    offset += SALT_SIZE

    nonce = payload_bytes[offset : offset + NONCE_SIZE]
    offset += NONCE_SIZE

    (cipher_len,) = struct.unpack(">I", payload_bytes[offset : offset + 4])
    offset += 4

    header = payload_bytes[:MODE_1_HEADER_SIZE]
    ciphertext_and_tag = payload_bytes[offset : offset + cipher_len]

    if len(ciphertext_and_tag) != cipher_len:
        raise InvalidPayloadError(
            f"Payload truncated: expected {cipher_len} bytes, got {len(ciphertext_and_tag)}"
        )

    enc_key, _ = _derive_symmetric_keys(password, salt)
    aesgcm = AESGCM(enc_key)

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=header)
    except InvalidTag as e:
        raise AuthenticationError("Decryption failed: incorrect password or tampered data.") from e

    return plaintext


def encrypt_asymmetric(
    plaintext: bytes | str,
    recipient_public_key: x25519.X25519PublicKey,
) -> tuple[bytes, bytes]:
    """Encrypt plaintext using X25519 ECDH key exchange and AES-256-GCM.
    
    Generates an ephemeral sender keypair.
    
    Returns:
        tuple[bytes, bytes]: (full_payload_bytes, permutation_key)
    """
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    if not plaintext:
        raise ValueError("Plaintext cannot be empty.")
    if not isinstance(recipient_public_key, x25519.X25519PublicKey):
        raise TypeError("recipient_public_key must be an instance of X25519PublicKey.")

    # Generate ephemeral sender keypair
    sender_priv = x25519.X25519PrivateKey.generate()
    sender_pub = sender_priv.public_key()
    eph_pub_bytes = sender_pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    shared_secret = sender_priv.exchange(recipient_public_key)
    enc_key, _ = _derive_asymmetric_keys(shared_secret)
    perm_key = derive_permutation_key_from_public_key(recipient_public_key)

    nonce = os.urandom(NONCE_SIZE)
    cipher_len = len(plaintext) + TAG_SIZE

    # Header: Magic(4) + Version(1) + Mode(1) + EphPub(32) + Nonce(12) + Length(4)
    header = (
        MAGIC
        + bytes([VERSION, MODE_ASYMMETRIC])
        + eph_pub_bytes
        + nonce
        + struct.pack(">I", cipher_len)
    )

    aesgcm = AESGCM(enc_key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=header)

    full_payload = header + ciphertext_and_tag
    return full_payload, perm_key


def decrypt_asymmetric(
    payload_bytes: bytes,
    recipient_private_key: x25519.X25519PrivateKey,
) -> bytes:
    """Decrypt and authenticate an asymmetric payload using recipient's private key.
    
    Raises:
        InvalidPayloadError: If header validation fails.
        AuthenticationError: If AES-GCM authentication fails.
    """
    if not isinstance(recipient_private_key, x25519.X25519PrivateKey):
        raise TypeError("recipient_private_key must be an instance of X25519PrivateKey.")
    if len(payload_bytes) < MODE_2_HEADER_SIZE + TAG_SIZE:
        raise InvalidPayloadError("Payload is too short to be a valid StegoShield payload.")

    magic = payload_bytes[:4]
    if magic != MAGIC:
        raise InvalidPayloadError(f"Invalid magic bytes: expected {MAGIC!r}, got {magic!r}")

    version = payload_bytes[4]
    if version != VERSION:
        raise InvalidPayloadError(f"Unsupported protocol version: {version}")

    mode = payload_bytes[5]
    if mode != MODE_ASYMMETRIC:
        raise InvalidPayloadError(f"Expected asymmetric mode ({MODE_ASYMMETRIC}), got mode {mode}")

    offset = 6
    eph_pub_bytes = payload_bytes[offset : offset + X25519_KEY_SIZE]
    offset += X25519_KEY_SIZE

    nonce = payload_bytes[offset : offset + NONCE_SIZE]
    offset += NONCE_SIZE

    (cipher_len,) = struct.unpack(">I", payload_bytes[offset : offset + 4])
    offset += 4

    header = payload_bytes[:MODE_2_HEADER_SIZE]
    ciphertext_and_tag = payload_bytes[offset : offset + cipher_len]

    if len(ciphertext_and_tag) != cipher_len:
        raise InvalidPayloadError(
            f"Payload truncated: expected {cipher_len} bytes, got {len(ciphertext_and_tag)}"
        )

    eph_pub_key = x25519.X25519PublicKey.from_public_bytes(eph_pub_bytes)
    shared_secret = recipient_private_key.exchange(eph_pub_key)
    enc_key, _ = _derive_asymmetric_keys(shared_secret)

    aesgcm = AESGCM(enc_key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=header)
    except InvalidTag as e:
        raise AuthenticationError("Decryption failed: incorrect private key or tampered data.") from e

    return plaintext


def inspect_payload_header(payload_bytes: bytes) -> dict[str, Any]:
    """Parse header without decrypting to inspect metadata."""
    if len(payload_bytes) < 6:
        raise InvalidPayloadError("Payload too short for header inspection.")
    
    magic = payload_bytes[:4]
    if magic != MAGIC:
        raise InvalidPayloadError("Not a valid StegoShield payload.")
    
    version = payload_bytes[4]
    mode = payload_bytes[5]

    info: dict[str, Any] = {
        "magic": magic.decode("ascii", errors="replace"),
        "version": version,
        "mode": "password" if mode == MODE_PASSWORD else ("asymmetric" if mode == MODE_ASYMMETRIC else "unknown"),
        "mode_id": mode,
    }

    if mode == MODE_PASSWORD:
        if len(payload_bytes) < MODE_1_HEADER_SIZE:
            raise InvalidPayloadError("Mode 1 header truncated.")
        info["header_size"] = MODE_1_HEADER_SIZE
        info["salt"] = payload_bytes[6 : 6 + SALT_SIZE]
        info["nonce"] = payload_bytes[6 + SALT_SIZE : 6 + SALT_SIZE + NONCE_SIZE]
        (info["ciphertext_length"],) = struct.unpack(">I", payload_bytes[34:38])
    elif mode == MODE_ASYMMETRIC:
        if len(payload_bytes) < MODE_2_HEADER_SIZE:
            raise InvalidPayloadError("Mode 2 header truncated.")
        info["header_size"] = MODE_2_HEADER_SIZE
        info["ephemeral_public_key"] = payload_bytes[6 : 6 + X25519_KEY_SIZE]
        info["nonce"] = payload_bytes[6 + X25519_KEY_SIZE : 6 + X25519_KEY_SIZE + NONCE_SIZE]
        (info["ciphertext_length"],) = struct.unpack(">I", payload_bytes[50:54])

    return info

