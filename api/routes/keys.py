"""X25519 key pair generation and public-key inspection."""

from __future__ import annotations

import hashlib

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from fastapi import APIRouter

from api.errors import ApiError
from api.schemas import (
    ExampleKeyPairResponse,
    KeyGenerationRequest,
    KeyPairResponse,
    PublicKeyInfo,
    PublicKeyInspectRequest,
)
from core.keys import (
    example_keypair,
    export_private_key_pem,
    export_public_key_base64,
    export_public_key_pem,
    generate_keypair,
    import_public_key_auto,
    is_example_public_key,
)

FINGERPRINT_HEX_CHARS = 32
FINGERPRINT_GROUP_SIZE = 4
INVALID_PUBLIC_KEY_MESSAGE = (
    "That isn't a valid X25519 public key. Paste the whole key exactly as you received it (PEM, Base64 or hex)."
)

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.post("/generate", response_model=KeyPairResponse)
def generate_key_pair(request: KeyGenerationRequest) -> KeyPairResponse:
    """Create a key pair. Nothing is stored: the private key exists only in this response."""
    private_key, public_key = generate_keypair()
    passphrase = request.passphrase or None
    return KeyPairResponse(
        public_key_base64=export_public_key_base64(public_key),
        public_key_pem=export_public_key_pem(public_key),
        private_key_pem=export_private_key_pem(private_key, password=passphrase),
        fingerprint=fingerprint_of(public_key),
        is_private_key_encrypted=passphrase is not None,
    )


@router.get("/example", response_model=ExampleKeyPairResponse)
def example_key_pair() -> ExampleKeyPairResponse:
    """The fixed example key pair for trying public-key mode. Everyone has its private key: testing only."""
    private_key, public_key = example_keypair()
    return ExampleKeyPairResponse(
        public_key_base64=export_public_key_base64(public_key),
        public_key_pem=export_public_key_pem(public_key),
        private_key_pem=export_private_key_pem(private_key),
        fingerprint=fingerprint_of(public_key),
    )


@router.post("/inspect", response_model=PublicKeyInfo)
def inspect_public_key(request: PublicKeyInspectRequest) -> PublicKeyInfo:
    """Validate a public key and return its fingerprint so both sides can compare it."""
    public_key = parse_public_key(request.public_key, field="public_key")
    return PublicKeyInfo(
        public_key_base64=export_public_key_base64(public_key),
        fingerprint=fingerprint_of(public_key),
        is_example_key=is_example_public_key(public_key),
    )


def parse_public_key(text: str, field: str) -> x25519.X25519PublicKey:
    """Parse a PEM, Base64 or hex public key.

    Raises:
        ApiError: The text is not a valid X25519 public key.
    """
    try:
        return import_public_key_auto(text)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise ApiError(422, "invalid_key", INVALID_PUBLIC_KEY_MESSAGE, field=field) from exc


def fingerprint_of(public_key: x25519.X25519PublicKey) -> str:
    """Short SHA-256 fingerprint of the raw key, grouped for reading aloud: 'AB12 CD34 …'."""
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    digest = hashlib.sha256(raw).hexdigest()[:FINGERPRINT_HEX_CHARS].upper()
    groups = [digest[i : i + FINGERPRINT_GROUP_SIZE] for i in range(0, len(digest), FINGERPRINT_GROUP_SIZE)]
    return " ".join(groups)
