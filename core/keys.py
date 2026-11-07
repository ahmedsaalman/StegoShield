"""StegoShield Asymmetric Key Management (Module A).

Helpers for X25519 keypair generation, PEM/Base64/Hex export, and robust import.
"""

from __future__ import annotations

import base64
from typing import Tuple, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519


def generate_keypair() -> tuple[x25519.X25519PrivateKey, x25519.X25519PublicKey]:
    """Generate a new cryptographic X25519 keypair."""
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def export_private_key_pem(
    private_key: x25519.X25519PrivateKey,
    password: str | None = None,
) -> str:
    """Export an X25519 private key to PKCS#8 PEM format (optionally encrypted)."""
    encryption: serialization.KeySerializationEncryption
    if password:
        encryption = serialization.BestAvailableEncryption(password.encode("utf-8"))
    else:
        encryption = serialization.NoEncryption()

    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    return pem_bytes.decode("utf-8")


def import_private_key_pem(
    pem_str: str,
    password: str | None = None,
) -> x25519.X25519PrivateKey:
    """Import an X25519 private key from a PKCS#8 PEM string."""
    pw_bytes = password.encode("utf-8") if password else None
    key = serialization.load_pem_private_key(pem_str.encode("utf-8"), password=pw_bytes)
    if not isinstance(key, x25519.X25519PrivateKey):
        raise TypeError(f"Loaded key is not an X25519 private key (got {type(key).__name__}).")
    return key


def export_public_key_pem(public_key: x25519.X25519PublicKey) -> str:
    """Export an X25519 public key to SubjectPublicKeyInfo PEM format."""
    pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_bytes.decode("utf-8")


def import_public_key_pem(pem_str: str) -> x25519.X25519PublicKey:
    """Import an X25519 public key from a SubjectPublicKeyInfo PEM string."""
    key = serialization.load_pem_public_key(pem_str.encode("utf-8"))
    if not isinstance(key, x25519.X25519PublicKey):
        raise TypeError(f"Loaded key is not an X25519 public key (got {type(key).__name__}).")
    return key


def export_public_key_base64(public_key: x25519.X25519PublicKey) -> str:
    """Export raw 32-byte public key as URL-safe / standard Base64 string."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def import_public_key_base64(b64_str: str) -> x25519.X25519PublicKey:
    """Import raw 32-byte public key from Base64 string."""
    raw = base64.b64decode(b64_str.strip())
    if len(raw) != 32:
        raise ValueError(f"Invalid raw X25519 public key length: expected 32 bytes, got {len(raw)}")
    return x25519.X25519PublicKey.from_public_bytes(raw)


def import_public_key_auto(key_str: str) -> x25519.X25519PublicKey:
    """Auto-detect format (PEM, Base64, or Hex) and load X25519 public key."""
    cleaned = key_str.strip()
    if "BEGIN PUBLIC KEY" in cleaned:
        return import_public_key_pem(cleaned)

    # Try hex string (64 characters)
    if len(cleaned) == 64:
        try:
            raw = bytes.fromhex(cleaned)
            return x25519.X25519PublicKey.from_public_bytes(raw)
        except ValueError:
            pass

    # Try base64
    try:
        return import_public_key_base64(cleaned)
    except Exception as e:
        raise ValueError(
            "Could not parse public key. Must be valid PEM, 32-byte Base64, or 64-char Hex."
        ) from e

