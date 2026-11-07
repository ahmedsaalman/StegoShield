"""End-to-End Pipeline Integration Tests (Task L15).

Verifies full flow:
Encrypt -> Embed -> Save PNG -> Load PNG -> Extract -> Authenticate & Decrypt.
Tests both Password mode and X25519 Asymmetric mode.
"""

import io
import pytest
from PIL import Image
import numpy as np

from core.pipeline import (
    stego_encode_password,
    stego_decode_password,
    stego_encode_asymmetric,
    stego_decode_asymmetric,
)
from core.keys import generate_keypair
from core.crypto import AuthenticationError, InvalidPayloadError, StegoCryptoError


@pytest.fixture
def test_image():
    """Create a 150x150 RGB PNG in memory."""
    rng = np.random.default_rng(999)
    arr = rng.integers(30, 220, size=(150, 150, 3), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def test_password_pipeline_png_roundtrip(test_image):
    """Test full encrypt-embed-save-load-extract-decrypt cycle in password mode."""
    secret = "StegoShield End-to-End Secure Message! 🛡️🔐"
    password = "SuperSecretPassword#2026"

    # Encode & produce PNG
    stego_img = stego_encode_password(test_image, secret, password)
    
    # Save to byte buffer (simulates saving/loading from disk as PNG)
    buf = io.BytesIO()
    stego_img.save(buf, format="PNG")
    buf.seek(0)

    # Load and decode
    loaded_stego = Image.open(buf)
    recovered_bytes = stego_decode_password(loaded_stego, password)

    assert recovered_bytes.decode("utf-8") == secret


def test_password_pipeline_wrong_password_fails(test_image):
    """Wrong password must raise AuthenticationError or InvalidPayloadError (safe failure)."""
    secret = "Sensitive content"
    stego_img = stego_encode_password(test_image, secret, "CorrectPass1")

    buf = io.BytesIO()
    stego_img.save(buf, format="PNG")
    buf.seek(0)
    loaded_stego = Image.open(buf)

    with pytest.raises((AuthenticationError, InvalidPayloadError)):
        stego_decode_password(loaded_stego, "WrongPass2")


def test_asymmetric_pipeline_png_roundtrip(test_image):
    """Test full cycle in X25519 asymmetric mode."""
    alice_priv, alice_pub = generate_keypair()
    secret = "Classified intelligence for Alice only."

    # Sender encodes with Alice's public key
    stego_img = stego_encode_asymmetric(test_image, secret, alice_pub)

    buf = io.BytesIO()
    stego_img.save(buf, format="PNG")
    buf.seek(0)

    # Alice decodes with her private key
    loaded_stego = Image.open(buf)
    recovered = stego_decode_asymmetric(loaded_stego, alice_priv)

    assert recovered.decode("utf-8") == secret


def test_asymmetric_pipeline_wrong_key_fails(test_image):
    """Bob attempting to decode Alice's stego image must fail safely."""
    alice_priv, alice_pub = generate_keypair()
    bob_priv, bob_pub = generate_keypair()

    stego_img = stego_encode_asymmetric(test_image, "Secret for Alice", alice_pub)

    buf = io.BytesIO()
    stego_img.save(buf, format="PNG")
    buf.seek(0)
    loaded_stego = Image.open(buf)

    with pytest.raises((AuthenticationError, InvalidPayloadError)):
        stego_decode_asymmetric(loaded_stego, bob_priv)

