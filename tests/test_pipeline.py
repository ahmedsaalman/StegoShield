"""End-to-End Pipeline Integration Tests (Task L15).

Verifies full flow:
Encrypt -> Embed -> Save PNG -> Load PNG -> Extract -> Authenticate & Decrypt.
Tests both Password mode and X25519 Asymmetric mode.
"""

import io

import numpy as np
import pytest
from PIL import Image

from core.crypto import AuthenticationError, InvalidPayloadError
from core.keys import generate_keypair
from core.pipeline import (
    main,
    stego_decode_asymmetric,
    stego_decode_password,
    stego_encode_asymmetric,
    stego_encode_password,
)


@pytest.fixture
def test_image():
    """Create a 150x150 RGB PNG in memory."""
    rng = np.random.default_rng(999)
    arr = rng.integers(30, 220, size=(150, 150, 3), dtype=np.uint8)
    return Image.fromarray(arr)


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


# --- command-line interface -------------------------------------------------------------------------


@pytest.fixture
def cover_file(test_image, tmp_path):
    path = tmp_path / "cover.png"
    test_image.save(path)
    return path


def test_cli_password_round_trip_prints_the_message(cover_file, tmp_path, capsys):
    stego = tmp_path / "stego.png"

    hide_code = main(
        ["hide-pass", "--cover", str(cover_file), "--message", "hi there", "--password", "pw-1", "--out", str(stego)]
    )
    reveal_code = main(["extract-pass", "--stego", str(stego), "--password", "pw-1"])

    assert (hide_code, reveal_code) == (0, 0)
    assert "[+] Secret Message: hi there" in capsys.readouterr().out


def test_cli_wrong_password_prints_one_line_error_without_traceback(cover_file, tmp_path, capsys):
    stego = tmp_path / "stego.png"
    main(["hide-pass", "--cover", str(cover_file), "--message", "hi", "--password", "right-pw", "--out", str(stego)])

    exit_code = main(["extract-pass", "--stego", str(stego), "--password", "wrong-pw"])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert err.startswith("[!] No hidden message could be recovered")
    assert "Traceback" not in err and "wrong-pw" not in err


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["hide-pass", "--message", "x" * 20000, "--password", "p", "--out", "{tmp}/o.png"], "can hold at most"),
        (
            ["hide-asym", "--message", "hi", "--pubkey", "not-a-key", "--out", "{tmp}/o.png"],
            "Could not parse public key",
        ),
        (["capacity", "--cover", "{tmp}/missing.png"], "missing.png"),
    ],
)
def test_cli_expected_failures_exit_1_with_a_message(cover_file, tmp_path, capsys, args, expected):
    args = [arg.replace("{tmp}", str(tmp_path)) for arg in args]
    if args[0] != "capacity":
        args[1:1] = ["--cover", str(cover_file)]

    exit_code = main(args)

    err = capsys.readouterr().err
    assert exit_code == 1
    assert expected in err and "Traceback" not in err
