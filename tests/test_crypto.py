"""Unit tests for the StegoShield cryptographic engine (Module A, format v2).

- Round trips in password and X25519 modes.
- Wrong password / wrong private key is rejected.
- Any modified byte (stage 1, nonce, length, ciphertext, tag) is rejected.
- The packet carries no plaintext markers.
- Key import/export formats.
"""

import pytest
from cryptography.hazmat.primitives import serialization

from core import crypto
from core.crypto import (
    MAGIC,
    MODE_ASYMMETRIC,
    MODE_PASSWORD,
    SALT_SIZE,
    X25519_KEY_SIZE,
    AuthenticationError,
    InvalidPayloadError,
    decrypt_asymmetric,
    decrypt_password,
    derive_password_session,
    encrypt_asymmetric,
    encrypt_password,
    locator_key_from_password,
    locator_key_from_public_key,
    packet_overhead,
)
from core.keys import (
    export_private_key_pem,
    export_public_key_base64,
    export_public_key_pem,
    generate_keypair,
    import_private_key_pem,
    import_public_key_auto,
)

# ==============================================================================
# Password Mode
# ==============================================================================


@pytest.mark.real_kdf
def test_password_key_derivation_runs_600k_pbkdf2_rounds(monkeypatch):
    """The rest of the suite uses 1,000 rounds for speed (tests/conftest.py); production must not."""
    rounds = []
    real_pbkdf2 = crypto.PBKDF2HMAC

    def recording_pbkdf2(*args, **kwargs):
        rounds.append(kwargs["iterations"])
        return real_pbkdf2(*args, **kwargs)

    monkeypatch.setattr(crypto, "PBKDF2HMAC", recording_pbkdf2)
    derive_password_session("correct horse", b"\x00" * SALT_SIZE)

    assert rounds == [600_000]


def test_password_mode_round_trip():
    secret = "TopSecretStegoMessage 12345! @#$%"
    packet = encrypt_password(secret, "CorrectHorseBatteryStaple#99")
    assert len(packet) == len(secret) + packet_overhead(MODE_PASSWORD)
    assert decrypt_password(packet, "CorrectHorseBatteryStaple#99").decode() == secret


def test_password_mode_binary_round_trip():
    secret = bytes(range(256))
    assert decrypt_password(encrypt_password(secret, "BinaryPassword123!"), "BinaryPassword123!") == secret


def test_password_mode_wrong_password_fails():
    packet = encrypt_password("Sensitive Information", "CorrectPassword123")
    with pytest.raises(AuthenticationError):
        decrypt_password(packet, "WrongPassword123")


@pytest.mark.parametrize(
    "offset, region",
    [(0, "salt"), (SALT_SIZE + 3, "nonce"), (SALT_SIZE + 13, "masked length"), (-20, "ciphertext"), (-1, "tag")],
)
def test_password_mode_any_byte_tampering_fails(offset, region):
    """Flipping a bit anywhere in the packet must be rejected."""
    packet = bytearray(encrypt_password("IntegrityProtectedData", "SafePassword"))
    packet[offset] ^= 0x01
    with pytest.raises(AuthenticationError):
        decrypt_password(bytes(packet), "SafePassword")


def test_password_mode_truncated_packet():
    with pytest.raises(InvalidPayloadError):
        decrypt_password(b"short", "password")


def test_password_packets_are_randomised():
    """Same message + password twice gives unrelated packets (fresh salt and nonce)."""
    a = encrypt_password("same", "pw")
    b = encrypt_password("same", "pw")
    assert a[:SALT_SIZE] != b[:SALT_SIZE]
    assert a != b


# ==============================================================================
# Asymmetric Mode (X25519)
# ==============================================================================


def test_asymmetric_mode_round_trip():
    alice_priv, alice_pub = generate_keypair()
    packet = encrypt_asymmetric("AsymmetricSecretFromSender", alice_pub)
    assert len(packet) == len("AsymmetricSecretFromSender") + packet_overhead(MODE_ASYMMETRIC)
    assert decrypt_asymmetric(packet, alice_priv) == b"AsymmetricSecretFromSender"


def test_asymmetric_mode_wrong_private_key_fails():
    _, alice_pub = generate_keypair()
    bob_priv, _ = generate_keypair()
    with pytest.raises(AuthenticationError):
        decrypt_asymmetric(encrypt_asymmetric("SecretForAlice", alice_pub), bob_priv)


@pytest.mark.parametrize("offset", [5, X25519_KEY_SIZE - 1, X25519_KEY_SIZE + 2, -1])
def test_asymmetric_mode_tampering_fails(offset):
    """Tampering with the one-time key (including its random top bit) or the body is rejected."""
    alice_priv, alice_pub = generate_keypair()
    packet = bytearray(encrypt_asymmetric("SecretForAlice", alice_pub))
    packet[offset] ^= 0x80
    with pytest.raises(AuthenticationError):
        decrypt_asymmetric(bytes(packet), alice_priv)


def test_asymmetric_top_bit_is_randomised():
    """The embedded one-time key must not have a constant top bit (X25519 keys always have it 0)."""
    _, pub = generate_keypair()
    top_bits = {encrypt_asymmetric("x", pub)[X25519_KEY_SIZE - 1] >> 7 for _ in range(40)}
    assert top_bits == {0, 1}


# ==============================================================================
# No plaintext markers & key separation
# ==============================================================================


def test_packets_contain_no_magic_bytes():
    _, pub = generate_keypair()
    for _ in range(3):
        assert MAGIC not in encrypt_password("hello", "pw")
        assert MAGIC not in encrypt_asymmetric("hello", pub)


def test_session_subkeys_are_independent():
    keys = derive_password_session("MasterPassword2026", b"\x00" * 16)
    assert len({keys.enc_key, keys.slot_key}) == 2
    assert len(keys.enc_key) == len(keys.slot_key) == 32 and len(keys.mask_key) == 4
    # Locator key is unrelated to the PBKDF2-derived keys
    assert locator_key_from_password("MasterPassword2026") not in (keys.enc_key, keys.slot_key)


def test_locator_keys_are_deterministic_and_distinct():
    assert locator_key_from_password("a") == locator_key_from_password("a")
    assert locator_key_from_password("a") != locator_key_from_password("b")
    _, p1 = generate_keypair()
    _, p2 = generate_keypair()
    assert locator_key_from_public_key(p1) != locator_key_from_public_key(p2)


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

    with pytest.raises(ValueError):
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
    assert (
        loaded_from_pem.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        == raw_pub_bytes
    )

    # Base64
    b64_str = export_public_key_base64(pub)
    loaded_from_b64 = import_public_key_auto(b64_str)
    assert (
        loaded_from_b64.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        == raw_pub_bytes
    )

    # Hex
    hex_str = raw_pub_bytes.hex()
    loaded_from_hex = import_public_key_auto(hex_str)
    assert (
        loaded_from_hex.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        == raw_pub_bytes
    )
