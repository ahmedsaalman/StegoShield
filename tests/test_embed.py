"""Unit tests for StegoShield Steganographic Embedding & Extraction (Module C).

Covers Task L14:
- Bit/byte conversion round trip.
- Round-trip embedding and extraction across RGB, RGBA, and Grayscale images.
- LSB replacement and LSB matching (+/-1) modes.
- Sequential and pseudorandom permutation modes.
- Wrong permutation key fails safely.
- Over-capacity rejection (CapacityExceededError).
- Maximum pixel distortion verification (diff <= 1).
"""

import pytest
import numpy as np
from PIL import Image

from core.embed import (
    bytes_to_bits,
    bits_to_bytes,
    generate_carrier_permutation,
    embed_payload,
    extract_payload,
)
from core.capacity import calculate_image_capacity, check_capacity, CapacityExceededError
from core.crypto import InvalidPayloadError


def create_synthetic_image(width=100, height=100, mode="RGB", pattern="gradient") -> Image.Image:
    """Create a synthetic test image."""
    if pattern == "gradient":
        x = np.linspace(0, 255, width, dtype=np.uint8)
        y = np.linspace(0, 255, height, dtype=np.uint8)
        xx, yy = np.meshgrid(x, y)
        if mode == "RGB":
            arr = np.stack([xx, yy, (xx // 2 + yy // 2).astype(np.uint8)], axis=-1)
        elif mode == "RGBA":
            alpha = np.full((height, width), 255, dtype=np.uint8)
            arr = np.stack([xx, yy, (xx // 2 + yy // 2).astype(np.uint8), alpha], axis=-1)
        else:  # 'L'
            arr = ((xx.astype(np.uint16) + yy.astype(np.uint16)) // 2).astype(np.uint8)
    else:
        rng = np.random.default_rng(1234)
        channels = 4 if mode == "RGBA" else (3 if mode == "RGB" else 1)
        arr = rng.integers(0, 256, size=(height, width, channels) if channels > 1 else (height, width), dtype=np.uint8)

    return Image.fromarray(arr, mode=mode)


# ==============================================================================
# Bit/Byte Tests (L08)
# ==============================================================================

def test_bits_bytes_round_trip():
    """Verify bit packing and unpacking."""
    raw = b"StegoShield Bit Test \x00\xff\xaa\x55"
    bits = bytes_to_bits(raw)
    assert len(bits) == len(raw) * 8
    recovered = bits_to_bytes(bits)
    assert recovered == raw


# ==============================================================================
# Embedding Round-Trip Tests (L10, L11, L12)
# ==============================================================================

@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L"])
@pytest.mark.parametrize("algo", ["replacement", "matching"])
def test_embed_extract_pseudorandom(mode, algo):
    """Verify round-trip with pseudorandom permutation."""
    img = create_synthetic_image(120, 80, mode=mode)
    payload = b"Hello from StegoShield Pseudorandom LSB test!"
    perm_key = b"A" * 32

    stego_img = embed_payload(img, payload, perm_key=perm_key, mode="pseudorandom", algorithm=algo)
    extracted = extract_payload(stego_img, perm_key=perm_key, mode="pseudorandom")

    assert extracted == payload


def test_embed_extract_sequential():
    """Verify round-trip with sequential embedding."""
    img = create_synthetic_image(80, 80, mode="RGB")
    payload = b"Sequential embedding test payload."

    stego_img = embed_payload(img, payload, mode="sequential", algorithm="replacement")
    extracted = extract_payload(stego_img, mode="sequential")

    assert extracted == payload


def test_pixel_distortion_bounds():
    """Verify that stego modification modifies pixels by at most 1 unit."""
    img = create_synthetic_image(100, 100, mode="RGB", pattern="gradient")
    payload = b"Testing strict pixel bounds!" * 20
    perm_key = b"B" * 32

    stego_rep = embed_payload(img, payload, perm_key=perm_key, algorithm="replacement")
    diff_rep = np.abs(np.array(stego_rep, dtype=np.int16) - np.array(img, dtype=np.int16))
    assert np.max(diff_rep) <= 1

    stego_mat = embed_payload(img, payload, perm_key=perm_key, algorithm="matching")
    diff_mat = np.abs(np.array(stego_mat, dtype=np.int16) - np.array(img, dtype=np.int16))
    assert np.max(diff_mat) <= 1


def test_rgba_alpha_channel_preserved():
    """Verify that Alpha channel is preserved unmodified in RGBA images."""
    img = create_synthetic_image(60, 60, mode="RGBA")
    payload = b"Protect the alpha transparency channel"
    perm_key = b"C" * 32

    stego_img = embed_payload(img, payload, perm_key=perm_key)

    orig_arr = np.array(img)
    stego_arr = np.array(stego_img)

    # Alpha channel (index 3) must be 100% identical
    assert np.array_equal(orig_arr[:, :, 3], stego_arr[:, :, 3])


def test_wrong_permutation_key_fails_safely():
    """Extracting with the wrong key must fail safely without leaking."""
    img = create_synthetic_image(100, 100, mode="RGB")
    payload = b"Secret payload to protect"
    correct_key = b"1" * 32
    wrong_key = b"2" * 32

    stego_img = embed_payload(img, payload, perm_key=correct_key, mode="pseudorandom")

    # With wrong key, reading random bits as length header will either
    # exceed capacity or raise InvalidPayloadError
    try:
        extracted = extract_payload(stego_img, perm_key=wrong_key, mode="pseudorandom")
        # If by astronomical chance it extracts something, it must not match payload
        assert extracted != payload
    except InvalidPayloadError:
        pass  # Expected safe failure


def test_over_capacity_rejection():
    """Embedding a payload larger than image capacity must raise CapacityExceededError."""
    tiny_img = create_synthetic_image(10, 10, mode="L")  # 100 slots, max bytes = (100 - 32) // 8 = 8 bytes
    huge_payload = b"This payload is definitely way too large for a 10x10 grayscale image"

    with pytest.raises(CapacityExceededError):
        embed_payload(tiny_img, huge_payload)

