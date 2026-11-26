"""Security, integrity and attack tests (format v2).

Each test maps to one row of tests/security_results.md:
1. Pixel tampering of a stego image is rejected.
2. Cropping is rejected cleanly.
3. Wrong password / wrong private key is rejected.
4. Public key alone can't locate or confirm a message (regression for the v1 leak).
5. A password guess can't be confirmed without paying PBKDF2 (regression for the v1 shortcut).
6. No plaintext marker is written anywhere in the image.
7. Two messages with the same password use different stage-2 positions.
"""

import numpy as np
import pytest
from PIL import Image
from scipy import stats

from core.crypto import (
    MAGIC,
    SALT_SIZE,
    STAGE2_HEADER_SIZE,
    X25519_KEY_SIZE,
    AuthenticationError,
    derive_password_session,
    locator_key_from_password,
    locator_key_from_public_key,
)
from core.embed import bits_to_bytes, image_to_carrier, read_bits, select_slots
from core.keys import generate_keypair
from core.pipeline import (
    stego_decode_asymmetric,
    stego_decode_password,
    stego_encode_asymmetric,
    stego_encode_password,
)


@pytest.fixture
def carrier_image() -> Image.Image:
    rng = np.random.default_rng(777)
    return Image.fromarray(rng.integers(20, 230, size=(120, 120, 3), dtype=np.uint8))


def _flat(img: Image.Image) -> np.ndarray:
    return image_to_carrier(img)[1]


def _read(flat: np.ndarray, count_bytes: int, key: bytes, exclude=None) -> bytes:
    slots = select_slots(len(flat), count_bytes * 8, key, exclude=exclude)
    return bits_to_bytes(read_bits(flat, slots))


# 1. Pixel tampering --------------------------------------------------------------


def test_pixel_tampering_is_rejected(carrier_image):
    stego = np.array(stego_encode_password(carrier_image, "Tamper resistance", "PixelPass#4"))
    stego[:60, :, :] ^= 0x01  # flip the LSB of every channel in the top half
    with pytest.raises(AuthenticationError):
        stego_decode_password(Image.fromarray(stego), "PixelPass#4")


def test_single_slot_tampering_is_rejected(carrier_image):
    """Flipping one embedded bit of the ciphertext is enough to reject the message."""
    password = "OneBitPass"
    stego = stego_encode_password(carrier_image, "one bit matters", password)
    arr, flat, _ = image_to_carrier(stego)
    s1 = select_slots(len(flat), SALT_SIZE * 8, locator_key_from_password(password))
    salt = bits_to_bytes(read_bits(flat, s1))
    keys = derive_password_session(password, salt)
    s2 = select_slots(len(flat), (STAGE2_HEADER_SIZE + 5) * 8, keys.slot_key, exclude=s1)
    flat[s2[-1]] ^= 1
    tampered = arr.copy()
    tampered[:] = flat.reshape(arr.shape)
    with pytest.raises(AuthenticationError):
        stego_decode_password(Image.fromarray(tampered), password)


# 2. Cropping ----------------------------------------------------------------------


def test_cropped_image_fails_safely(carrier_image):
    stego = stego_encode_password(carrier_image, "Resistant to cropping", "CropPass#5")
    w, h = stego.size
    with pytest.raises(AuthenticationError):
        stego_decode_password(stego.crop((0, 0, w // 2, h // 2)), "CropPass#5")


# 3. Wrong keys --------------------------------------------------------------------


def test_wrong_password_and_wrong_private_key(carrier_image):
    with pytest.raises(AuthenticationError):
        stego_decode_password(stego_encode_password(carrier_image, "x", "right"), "wrong")
    _, alice_pub = generate_keypair()
    eve_priv, _ = generate_keypair()
    with pytest.raises(AuthenticationError):
        stego_decode_asymmetric(stego_encode_asymmetric(carrier_image, "x", alice_pub), eve_priv)


# 4. Public key alone reveals nothing ---------------------------------------------


def test_public_key_holder_cannot_find_message(carrier_image):
    """v1 bug: positions came from the public key, so anyone could read 'STSH'.

    In v2 the public key only locates stage 1, which holds a random one-time key.
    It differs every time, and the rest of the message sits at positions that
    need the private key.
    """
    _, pub = generate_keypair()
    locator = locator_key_from_public_key(pub)
    seen = set()
    for _ in range(5):
        flat = _flat(stego_encode_asymmetric(carrier_image, "same message", pub))
        stage1 = _read(flat, X25519_KEY_SIZE, locator)
        assert MAGIC not in stage1
        seen.add(stage1)
    assert len(seen) == 5  # fresh random bytes each time: nothing constant to look for


# 5. Password guesses can't be confirmed cheaply -----------------------------------


def test_password_guess_cannot_be_confirmed_without_pbkdf2(carrier_image):
    """v1 bug: a guess could be checked by reading 'STSH' at cheap HKDF positions.

    In v2 the cheap locator only reaches stage 1 (a random salt). The salt
    changes with every message, so it can't confirm a guess. Everything else
    needs the PBKDF2 output.
    """
    password = "hunter2"
    locator = locator_key_from_password(password)
    salts = {_read(_flat(stego_encode_password(carrier_image, "same", password)), SALT_SIZE, locator) for _ in range(5)}
    assert len(salts) == 5
    assert all(MAGIC not in s for s in salts)


# 6. No plaintext marker anywhere ---------------------------------------------------


@pytest.mark.parametrize("layout", ["pseudorandom", "sequential"])
def test_no_magic_bytes_in_image(carrier_image, layout):
    """Even the sequential baseline (first slots in order) must not expose a marker."""
    _, pub = generate_keypair()
    for stego in (
        stego_encode_password(carrier_image, "find me", "pw", mode=layout),
        stego_encode_asymmetric(carrier_image, "find me", pub, mode=layout),
    ):
        flat = _flat(stego)
        sequential_read = bits_to_bytes(read_bits(flat, np.arange(len(flat) - len(flat) % 8)))
        assert MAGIC not in sequential_read


# 6b. Embedded bits look random -------------------------------------------------------

RANDOMNESS_ALPHA = 0.01


def _passes_randomness_checks(data: bytes) -> bool:
    """Monobit (share of 1-bits) and byte-frequency chi-square, both at alpha = 0.01."""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    monobit_p = stats.binomtest(int(bits.sum()), len(bits), 0.5).pvalue
    byte_counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    chi_square_p = stats.chisquare(byte_counts).pvalue
    return monobit_p > RANDOMNESS_ALPHA and chi_square_p > RANDOMNESS_ALPHA


def test_embedded_bits_pass_randomness_checks():
    """A highly repetitive message must still embed as random-looking bits.

    Uses the sequential layout so the bits can be read in order WITHOUT any key.
    Each check fails 1% of the time by chance even on true random data, so we
    require 2 of 3 independent stego images to pass.
    """
    rng = np.random.default_rng(5)
    cover = Image.fromarray(rng.integers(0, 256, size=(160, 160, 3), dtype=np.uint8))
    message = "A" * 6_000
    packet_bytes = 16 + 12 + 4 + len(message) + 16

    passes = 0
    for _ in range(3):
        flat = _flat(stego_encode_password(cover, message, "pw", mode="sequential"))
        passes += _passes_randomness_checks(bits_to_bytes(read_bits(flat, np.arange(packet_bytes * 8))))
    assert passes >= 2
    assert _passes_randomness_checks(np.random.default_rng(6).bytes(packet_bytes))  # control: real random data


# 7. Positions differ per message -------------------------------------------------------


def test_same_password_uses_different_positions(carrier_image):
    """Stage-2 positions depend on the per-message salt, so two messages don't line up."""
    password = "reuse"
    locator = locator_key_from_password(password)
    position_sets = []
    for _ in range(2):
        flat = _flat(stego_encode_password(carrier_image, "msg", password))
        s1 = select_slots(len(flat), SALT_SIZE * 8, locator)
        keys = derive_password_session(password, bits_to_bytes(read_bits(flat, s1)))
        position_sets.append(select_slots(len(flat), 256, keys.slot_key, exclude=s1))
    overlap = len(np.intersect1d(position_sets[0], position_sets[1]))
    assert overlap < 32  # random overlap of 256 of ~43k slots is ~1-2
