"""StegoShield Steganographic Embedding & Extraction Engine (Module C).

Low-level building blocks:
- Bit/byte conversion.
- Key-seeded slot selection: picks only the carrier slots that are needed, in a
  deterministic order, optionally excluding slots already taken.
- Writing/reading bits with LSB replacement or LSB matching (+/-1).
- A simple length-prefixed embed/extract pair, used by the ML dataset generator
  and as a baseline. The secure two-stage message format lives in core/pipeline.py.

A "slot" is one 8-bit colour value: R, G or B of one pixel (alpha is never touched).
"""

from __future__ import annotations

import struct
from typing import Literal

import numpy as np
from PIL import Image

from core.capacity import CapacityExceededError, check_capacity
from core.crypto import InvalidPayloadError

EmbeddingMode = Literal["pseudorandom", "sequential"]
EmbeddingAlgorithm = Literal["replacement", "matching"]


# ==============================================================================
# Bit / byte utilities
# ==============================================================================

def bytes_to_bits(data: bytes) -> np.ndarray:
    """Convert bytes to a 1D uint8 array of bits (MSB first)."""
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """Convert a 1D uint8 array of bits (MSB first) back into bytes."""
    if len(bits) % 8 != 0:
        raise ValueError(f"Bit length must be a multiple of 8, got {len(bits)} bits.")
    return np.packbits(bits).tobytes()


# ==============================================================================
# Slot selection
# ==============================================================================

def _bit_generator(key: bytes) -> np.random.PCG64:
    # SeedSequence + PCG64 raw output is stable across NumPy versions, so sender
    # and receiver pick the same slots even on different machines.
    return np.random.PCG64(np.random.SeedSequence(int.from_bytes(key, "big")))


def select_slots(
    total_slots: int,
    count: int,
    key: bytes | None = None,
    mode: EmbeddingMode = "pseudorandom",
    exclude: np.ndarray | None = None,
) -> np.ndarray:
    """Pick `count` distinct carrier slots.

    Pseudorandom mode walks a key-seeded random stream and keeps the first
    `count` slots not seen before and not in `exclude`. It only generates what
    it needs, so memory doesn't grow with image size.

    Prefix property: the first k slots of a request for n >= k slots equal a
    request for k slots. The receiver relies on this to read the header before
    it knows the message length.

    Args:
        total_slots: Number of carrier slots in the image.
        count: Number of slots wanted.
        key: Seed key (required for pseudorandom mode).
        mode: "pseudorandom" or "sequential" (baseline only).
        exclude: Slot indices that must not be returned.
    """
    used = np.zeros(total_slots, dtype=bool)
    if exclude is not None and len(exclude):
        used[exclude] = True
    free = total_slots - int(used.sum())
    if count > free:
        raise CapacityExceededError(f"Need {count} carrier slots but only {free} are free.")
    if count == 0:
        return np.empty(0, dtype=np.int64)

    if mode == "sequential" or key is None:
        return np.flatnonzero(~used)[:count].astype(np.int64)

    bitgen = _bit_generator(key)
    out = np.empty(count, dtype=np.int64)
    filled = 0
    while filled < count:
        need = count - filled
        free_now = total_slots - int(used.sum())
        # Draw enough candidates to cover duplicates and already-used slots.
        batch = max(1024, int(need * total_slots / free_now * 1.25) + 64)
        cand = (bitgen.random_raw(batch) % np.uint64(total_slots)).astype(np.int64)
        _, first = np.unique(cand, return_index=True)   # first occurrence of each slot...
        cand = cand[np.sort(first)]                      # ...kept in stream order
        cand = cand[~used[cand]][:need]
        used[cand] = True
        out[filled : filled + len(cand)] = cand
        filled += len(cand)
    return out


# ==============================================================================
# Carrier access
# ==============================================================================

def image_to_carrier(image: Image.Image) -> tuple[np.ndarray, np.ndarray, str]:
    """Return (full pixel array, flat copy of the embeddable channels, image mode)."""
    if image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGB")
    arr = np.array(image, dtype=np.uint8)
    view = arr[:, :, :3] if image.mode == "RGBA" else arr
    return arr, view.reshape(-1).copy(), image.mode


def carrier_to_image(arr: np.ndarray, flat: np.ndarray, img_mode: str) -> Image.Image:
    """Put modified carrier slots back into a new image (alpha untouched)."""
    out = arr.copy()
    if img_mode == "RGBA":
        out[:, :, :3] = flat.reshape(arr[:, :, :3].shape)
    else:
        out = flat.reshape(arr.shape)
    return Image.fromarray(out)


def write_bits(
    flat: np.ndarray,
    slots: np.ndarray,
    bits: np.ndarray,
    algorithm: EmbeddingAlgorithm = "replacement",
    rng: np.random.Generator | None = None,
) -> None:
    """Write bits into the LSBs of the given slots, in place.

    replacement: set the LSB directly (p & 0xFE) | bit.
    matching:    if the LSB is wrong, randomly add or subtract 1 instead. This
                 avoids the pairs-of-values signature that LSB replacement leaves.
    """
    if algorithm == "replacement":
        flat[slots] = (flat[slots] & np.uint8(0xFE)) | bits
        return
    if algorithm != "matching":
        raise ValueError(f"Unknown embedding algorithm: {algorithm}")

    values = flat[slots].astype(np.int16)
    wrong = (values & 1) != bits
    if not np.any(wrong):
        return
    targets, vals = slots[wrong], values[wrong]
    rng = rng if rng is not None else np.random.default_rng()
    deltas = rng.choice(np.array([-1, 1], dtype=np.int16), size=len(vals))
    deltas[vals == 0] = 1
    deltas[vals == 255] = -1
    flat[targets] = (vals + deltas).astype(np.uint8)


def read_bits(flat: np.ndarray, slots: np.ndarray) -> np.ndarray:
    """Read the LSBs of the given slots."""
    return (flat[slots] & 1).astype(np.uint8)


# ==============================================================================
# Simple length-prefixed embedding (dataset generation / baseline)
# ==============================================================================

def embed_payload(
    cover_image: Image.Image,
    payload_bytes: bytes,
    perm_key: bytes | None = None,
    mode: EmbeddingMode = "pseudorandom",
    algorithm: EmbeddingAlgorithm = "replacement",
) -> Image.Image:
    """Embed raw bytes behind a 32-bit length prefix.

    This is NOT the secure message format (the length prefix is in the clear).
    Use core.pipeline for real messages. This function exists so the detector
    can be trained on the same pixel changes with controlled payload sizes.
    """
    check_capacity(cover_image, len(payload_bytes))
    arr, flat, img_mode = image_to_carrier(cover_image)
    bits = bytes_to_bits(struct.pack(">I", len(payload_bytes)) + payload_bytes)
    slots = select_slots(len(flat), len(bits), key=perm_key, mode=mode)
    rng = np.random.default_rng(int.from_bytes(perm_key[:16], "big")) if perm_key else np.random.default_rng(42)
    write_bits(flat, slots, bits, algorithm, rng)
    return carrier_to_image(arr, flat, img_mode)


def extract_payload(
    stego_image: Image.Image,
    perm_key: bytes | None = None,
    mode: EmbeddingMode = "pseudorandom",
) -> bytes:
    """Extract bytes written by embed_payload."""
    _, flat, _ = image_to_carrier(stego_image)
    total = len(flat)
    if total < 32:
        raise InvalidPayloadError("Image is too small to contain a payload.")

    (length,) = struct.unpack(">I", bits_to_bytes(read_bits(flat, select_slots(total, 32, perm_key, mode))))
    if length <= 0 or 32 + length * 8 > total:
        raise InvalidPayloadError(f"Length prefix ({length} bytes) is invalid or exceeds the carrier.")
    slots = select_slots(total, 32 + length * 8, perm_key, mode)
    return bits_to_bytes(read_bits(flat, slots[32:]))
