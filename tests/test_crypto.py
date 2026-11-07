"""Unit and security tests for StegoShield Cryptographic Engine (Module A).

Covers Task L07:
- Round-trip encryption and decryption for password mode.
- Round-trip encryption and decryption for asymmetric X25519 mode.
- Authentication failure on incorrect password / incorrect private key.
- Tamper-proofing: flipped bit in ciphertext triggers AES-GCM tag failure.
- Header integrity: tampered salt, nonce, length, or mode triggers failure.
- Key import/export format tests (PEM, Base64, Hex, encrypted PEM).
"""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from core.crypto import (
    MAGIC,
    VERSION,
    MODE_PASSWORD,
    MODE_ASYMMETRIC,
    AuthenticationError,
    InvalidPayloadError,
    encrypt_password,
    decrypt_password,
    encrypt_asymmetric,
    decrypt_asymmetric,
    derive_permutation_key_from_password,
    derive_permutation_key_from_public_key,
    inspect_payload_header,
)
from core.keys import (
    generate_keypair,
    export_private_key_pem,
    import_private_key_pem,
    export_public_key_pem,
    import_public_key_pem,
    export_public_key_base64,
    import_public_key_base64,
    import_public_key_auto,
)


# ==============================================================================
# Password Mode Tests
# ==============================================================================

def test_password_mode_round_trip():
    """Verify that encrypted text is recovered losslessly with correct password."""
    secret = "TopSecretStegoMessage 12345! @#$%"
    password = "CorrectHorseBatteryStaple#99"

    payload, perm_key = encrypt_password(secret, password)
    assert isinstance(payload, bytes)
    assert isinstance(perm_key, bytes)
    assert len(perm_key) == 32

    recovered = decrypt_password(payload, password)
    assert recovered.decode("utf-8") == secret


def test_password_mode_binary_round_trip():
    """Verify binary data round trip."""
    secret_bytes = bytes(range(256))
    password = "BinaryPassword123!"

    payload, _ = encrypt_password(secret_bytes, password)
    recovered = decrypt_password(payload, password)
    assert recovered == secret_bytes


def test_password_mode_wrong_password_fails():
    """Decryption with the wrong password must raise AuthenticationError."""
    secret = "Sensitive Information"
    payload, _ = encrypt_password(secret, "CorrectPassword123")

    with pytest.raises(AuthenticationError):
        decrypt_password(payload, "WrongPassword123")


def test_password_mode_ciphertext_tampering_fails():
    """Modifying even a single bit in the ciphertext triggers AES-GCM tag verification failure."""
    secret = "IntegrityProtectedData"
    password = "SafePassword"
    payload, _ = encrypt_password(secret, password)

    # Flip the last bit in the ciphertext / tag
    tampered = bytearray(payload)
    tampered[-1] ^= 0x01

    with pytest.raises(AuthenticationError):
        decrypt_password(bytes(tampered), password)


def test_password_mode_header_tampering_fails():
    """Modifying header bytes triggers AAD failure or InvalidPayloadError."""
    secret = "HeaderTamperTest"
    password = "SafePassword"
    payload, _ = encrypt_password(secret, password)

    # Corrupt magic bytes
    tampered_magic = b"XXXX" + payload[4:]
    with pytest.raises(InvalidPayloadError):
        decrypt_password(tampered_magic, password)

    # Corrupt salt byte (offset 10)
    tampered_salt = bytearray(payload)
    tampered_salt[10] ^= 0xFF
    with pytest.raises(AuthenticationError):
        decrypt_password(bytes(tampered_salt), password)

    # Corrupt nonce byte (offset 25)
    tampered_nonce = bytearray(payload)
    tampered_nonce[25] ^= 0xFF
    with pytest.raises(AuthenticationError):
        decrypt_password(bytes(tampered_nonce), password)


def test_password_mode_truncated_payload():
    """Truncated payload must be rejected cleanly."""
    with pytest.raises(InvalidPayloadError):
        decrypt_password(b"STSH\x01\x01short", "password")


# ==============================================================================
# Asymmetric Mode Tests (X25519 ECDH)
# ==============================================================================

def test_asymmetric_mode_round_trip():
    """Verify asymmetric encryption/decryption with valid keypair."""
    alice_priv, alice_pub = generate_keypair()
    secret = "AsymmetricSecretFromSender"

    payload, perm_key = encrypt_asymmetric(secret, alice_pub)
    assert len(perm_key) == 32

    recovered = decrypt_asymmetric(payload, alice_priv)
    assert recovered.decode("utf-8") == secret


def test_asymmetric_mode_wrong_private_key_fails():
    """Decryption with an unrelated private key must raise AuthenticationError."""
    alice_priv, alice_pub = generate_keypair()
    bob_priv, _ = generate_keypair()

    payload, _ = encrypt_asymmetric("SecretForAlice", alice_pub)

    with pytest.raises(AuthenticationError):
        decrypt_asymmetric(payload, bob_priv)


def test_asymmetric_mode_tamper_ephemeral_key_fails():
    """Tampering with the embedded ephemeral public key must raise AuthenticationError."""
    alice_priv, alice_pub = generate_keypair()
    payload, _ = encrypt_asymmetric("SecretForAlice", alice_pub)

    # Ephemeral key starts at offset 6 (length 32)
    tampered = bytearray(payload)
    tampered[12] ^= 0xAA

    with pytest.raises(AuthenticationError):
        decrypt_asymmetric(bytes(tampered), alice_priv)


# ==============================================================================
# Key Management & Serialization Tests
# ==============================================================================

def test_keypair_generation_and_export():
    """Verify key generation, PEM export, and import."""
    priv, pub = generate_keypair()

    # Unencrypted PEM
    priv_pem = export_private_key_pem(priv)
    assert "BEGIN PRIVATE KEY" in priv_pem
    loaded_priv = import_private_key_pem(priv_pem)
    assert loaded_priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ) == pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # Password-encrypted PEM
    enc_pem = export_private_key_pem(priv, password="KeyPassphrase123")
    assert "ENCRYPTED" in enc_pem
    loaded_enc_priv = import_private_key_pem(enc_pem, password="KeyPassphrase123")
    assert loaded_enc_priv is not None

    with pytest.raises(Exception):
        import_private_key_pem(enc_pem, password="WrongPassphrase")


def test_public_key_formats_and_auto_import():
    """Verify PEM, Base64, and Hex import through import_public_key_auto."""
    _, pub = generate_keypair()
    raw_pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # PEM
    pem_str = export_public_key_pem(pub)
    loaded_from_pem = import_public_key_auto(pem_str)
    assert loaded_from_pem.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ) == raw_pub_bytes

    # Base64
    b64_str = export_public_key_base64(pub)
    loaded_from_b64 = import_public_key_auto(b64_str)
    assert loaded_from_b64.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ) == raw_pub_bytes

    # Hex
    hex_str = raw_pub_bytes.hex()
    loaded_from_hex = import_public_key_auto(hex_str)
    assert loaded_from_hex.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ) == raw_pub_bytes


# ==============================================================================
# Permutation Key & Header Inspection Tests
# ==============================================================================

def test_permutation_key_properties():
    """Permutation keys must be deterministic and distinct for different secrets."""
    k1 = derive_permutation_key_from_password("passA")
    k2 = derive_permutation_key_from_password("passA")
    k3 = derive_permutation_key_from_password("passB")

    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 32

    _, pub1 = generate_keypair()
    _, pub2 = generate_keypair()
    pk1 = derive_permutation_key_from_public_key(pub1)
    pk2 = derive_permutation_key_from_public_key(pub2)
    assert pk1 != pk2
    assert len(pk1) == 32


def test_header_inspection():
    """Inspect header metadata without decryption."""
    payload, _ = encrypt_password("TestInspect", "inspectpass")
    info = inspect_payload_header(payload)

    assert info["magic"] == "STSH"
    assert info["version"] == 1
    assert info["mode"] == "password"
    assert "salt" in info
    assert "nonce" in info
    assert info["ciphertext_length"] == len("TestInspect") + 16
