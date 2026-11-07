"""StegoShield Steganographic Embedding & Extraction Engine (Module C).

Implements:
- Bit/byte conversion utilities and 32-bit length header serialization (Task L08).
- Key-seeded pseudorandom permutation generator (Task L09).
- Pseudorandom LSB replacement embedding & extraction on PNG (Task L10).
- LSB matching (+/-1) embedding mode to defeat pair-of-values attacks (Task L11).
- Sequential embedding mode for baseline comparison (Task L12).
"""

from __future__ import annotations

import struct
from typing import Tuple, Literal, Optional
from PIL import Image
import numpy as np

from core.capacity import check_capacity, get_embeddable_channels
from core.crypto import InvalidPayloadError


EmbeddingMode = Literal["pseudorandom", "sequential"]
EmbeddingAlgorithm = Literal["replacement", "matching"]


# ==============================================================================
# Bit / Byte Utilities (Task L08)
# ==============================================================================

def bytes_to_bits(data: bytes) -> np.ndarray:
    """Convert bytes to a 1D uint8 array of individual bits (0 or 1), MSB first."""
    byte_array = np.frombuffer(data, dtype=np.uint8)
    return np.unpackbits(byte_array)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """Convert a 1D uint8 array of bits back into bytes, MSB first."""
    if len(bits) % 8 != 0:
        raise ValueError(f"Bit length must be a multiple of 8, got {len(bits)} bits.")
    return np.packbits(bits).tobytes()


# ==============================================================================
# Permutation Generator (Task L09 & L12)
# ==============================================================================

def generate_carrier_permutation(
    total_slots: int,
    perm_key: bytes | None = None,
    mode: EmbeddingMode = "pseudorandom",
) -> np.ndarray:
    """Generate the carrier channel index mapping.
    
    In pseudorandom mode: Uses a cryptographically seeded PCG64 PRNG to generate a
    uniform random permutation of all carrier channel slots.
    In sequential mode: Returns np.arange(total_slots) for baseline comparison.
    """
    if mode == "sequential" or perm_key is None:
        return np.arange(total_slots, dtype=np.int64)

    # Convert 32-byte permutation key to integer entropy for SeedSequence
    entropy = int.from_bytes(perm_key, byteorder="big")
    seed_seq = np.random.SeedSequence(entropy)
    rng = np.random.default_rng(np.random.PCG64(seed_seq))
    return rng.permutation(total_slots)


# ==============================================================================
# Embedding & Extraction (Tasks L10, L11, L12)
# ==============================================================================

def embed_payload(
    cover_image: Image.Image,
    payload_bytes: bytes,
    perm_key: bytes | None = None,
    mode: EmbeddingMode = "pseudorandom",
    algorithm: EmbeddingAlgorithm = "replacement",
) -> Image.Image:
    """Embed an encrypted payload into a cover image using LSB steganography.
    
    Args:
        cover_image: Carrier PIL Image (PNG format recommended).
        payload_bytes: Encrypted payload bytes (from core.crypto).
        perm_key: 32-byte key for pseudorandom permutation (None for sequential).
        mode: "pseudorandom" or "sequential".
        algorithm: "replacement" (standard LSB) or "matching" (+/-1 embedding).
        
    Returns:
        Image.Image: New PIL Image containing the embedded payload.
        
    Raises:
        CapacityExceededError: If payload cannot fit in the carrier image.
    """
    check_capacity(cover_image, len(payload_bytes))

    # Convert cover image to numpy array
    img_mode = cover_image.mode
    if img_mode not in ("RGB", "RGBA", "L"):
        cover_image = cover_image.convert("RGB")
        img_mode = "RGB"

    img_arr = np.array(cover_image, dtype=np.uint8)

    # Extract embeddable channels
    if img_mode == "RGBA":
        carrier_view = img_arr[:, :, :3]
    elif img_mode == "RGB":
        carrier_view = img_arr
    else:  # 'L'
        carrier_view = img_arr

    flat_carrier = carrier_view.reshape(-1)
    total_slots = len(flat_carrier)

    # Prepare bitstream: 32-bit length header + payload bits
    length_header = struct.pack(">I", len(payload_bytes))
    full_data = length_header + payload_bytes
    bits_to_embed = bytes_to_bits(full_data)
    num_bits = len(bits_to_embed)

    # Generate permutation indices
    indices = generate_carrier_permutation(total_slots, perm_key, mode=mode)
    target_indices = indices[:num_bits]

    # Create a writable copy for modified channels
    mod_flat = flat_carrier.copy()

    if algorithm == "replacement":
        # Standard LSB replacement: (p & 0xFE) | bit
        mod_flat[target_indices] = (mod_flat[target_indices] & np.uint8(0xFE)) | bits_to_embed
    elif algorithm == "matching":
        # LSB Matching (+/-1 embedding)
        # Avoids statistical asymmetry of pairs of values (PoV)
        targets = mod_flat[target_indices].astype(np.int16)
        current_lsbs = targets & 1
        mismatch_mask = current_lsbs != bits_to_embed

        if np.any(mismatch_mask):
            mismatch_indices = target_indices[mismatch_mask]
            mismatch_values = targets[mismatch_mask]

            # Generate random +/- 1 decisions
            if perm_key is not None:
                decision_rng = np.random.default_rng(
                    np.random.PCG64(np.random.SeedSequence(int.from_bytes(perm_key[:16], "big")))
                )
            else:
                decision_rng = np.random.default_rng(42)

            deltas = decision_rng.choice(np.array([-1, 1], dtype=np.int16), size=len(mismatch_values))

            # Boundary corrections: 0 can only go to +1, 255 can only go to -1
            deltas[mismatch_values == 0] = 1
            deltas[mismatch_values == 255] = -1

            mod_flat[mismatch_indices] = (mismatch_values + deltas).astype(np.uint8)
    else:
        raise ValueError(f"Unknown embedding algorithm: {algorithm}")

    # Reconstruct modified image array
    if img_mode == "RGBA":
        stego_arr = img_arr.copy()
        stego_arr[:, :, :3] = mod_flat.reshape(carrier_view.shape)
    else:
        stego_arr = mod_flat.reshape(img_arr.shape)

    return Image.fromarray(stego_arr, mode=img_mode)


def extract_payload(
    stego_image: Image.Image,
    perm_key: bytes | None = None,
    mode: EmbeddingMode = "pseudorandom",
) -> bytes:
    """Extract embedded payload bytes from a stego-image.
    
    Args:
        stego_image: Carrier PIL Image.
        perm_key: 32-byte key used during embedding (None for sequential).
        mode: "pseudorandom" or "sequential".
        
    Returns:
        bytes: Extracted raw payload bytes.
        
    Raises:
        InvalidPayloadError: If the length header indicates invalid or corrupted data.
    """
    img_mode = stego_image.mode
    if img_mode not in ("RGB", "RGBA", "L"):
        stego_image = stego_image.convert("RGB")
        img_mode = "RGB"

    img_arr = np.array(stego_image, dtype=np.uint8)

    if img_mode == "RGBA":
        carrier_view = img_arr[:, :, :3]
    elif img_mode == "RGB":
        carrier_view = img_arr
    else:
        carrier_view = img_arr

    flat_carrier = carrier_view.reshape(-1)
    total_slots = len(flat_carrier)

    if total_slots < 32:
        raise InvalidPayloadError("Image carrier is too small to contain a StegoShield header.")

    indices = generate_carrier_permutation(total_slots, perm_key, mode=mode)

    # 1. Read first 32 bits for the 4-byte payload length header
    length_indices = indices[:32]
    length_bits = flat_carrier[length_indices] & 1
    length_bytes = bits_to_bytes(length_bits)
    (payload_length,) = struct.unpack(">I", length_bytes)

    # Check bounds
    total_payload_bits = payload_length * 8
    if payload_length <= 0 or 32 + total_payload_bits > total_slots:
        raise InvalidPayloadError(
            f"Extracted payload length header ({payload_length} bytes) is invalid or exceeds carrier capacity."
        )

    # 2. Extract payload bits
    payload_indices = indices[32 : 32 + total_payload_bits]
    payload_bits = flat_carrier[payload_indices] & 1
    return bits_to_bytes(payload_bits)
