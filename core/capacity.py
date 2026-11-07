"""StegoShield Cover Image Capacity Engine (Module B).

Calculates exact payload limits in bytes and evaluates capacity thresholds
based on image dimensions and channel configurations.
"""

from __future__ import annotations

from typing import Tuple, Dict, Any
from PIL import Image
import numpy as np


# Recommended safe payload ratios based on steganographic literature
SAFE_PAYLOAD_RATIO: float = 0.10      # <= 10% carrier capacity: low detectability risk
MODERATE_PAYLOAD_RATIO: float = 0.25  # 10% - 25%: moderate detectability risk
HIGH_PAYLOAD_RATIO: float = 0.50      # 25% - 50%: high detectability risk


class CapacityExceededError(ValueError):
    """Raised when the payload exceeds carrier image capacity."""
    pass


def get_embeddable_channels(image: Image.Image) -> int:
    """Return number of channels used for embedding.
    
    For RGB: 3 channels (R, G, B).
    For RGBA: 3 channels (R, G, B), preserving Alpha for transparency fidelity.
    For L (Grayscale): 1 channel.
    """
    mode = image.mode
    if mode in ("RGB", "RGBA"):
        return 3
    elif mode in ("L", "1"):
        return 1
    else:
        # Convert any other modes to RGB
        return 3


def calculate_image_capacity(image: Image.Image) -> dict[str, Any]:
    """Calculate the maximum and recommended payload capacity for an image.
    
    Returns:
        dict: Detailed capacity metrics including dimensions, max bytes, and safe limits.
    """
    width, height = image.size
    channels = get_embeddable_channels(image)
    total_slots = width * height * channels  # 1 bit per channel LSB

    # Deduct 4 bytes (32 bits) for the embedded length header
    max_payload_bits = max(0, total_slots - 32)
    max_payload_bytes = max_payload_bits // 8

    safe_bytes = int(max_payload_bytes * SAFE_PAYLOAD_RATIO)
    moderate_bytes = int(max_payload_bytes * MODERATE_PAYLOAD_RATIO)

    return {
        "width": width,
        "height": height,
        "channels": channels,
        "total_carrier_bits": total_slots,
        "max_payload_bytes": max_payload_bytes,
        "safe_payload_bytes": safe_bytes,
        "moderate_payload_bytes": moderate_bytes,
        "recommended_max_bytes": safe_bytes,
    }


def compute_payload_ratio(payload_bytes: int, total_carrier_bits: int) -> float:
    """Compute the payload ratio: (payload_bits) / (carrier_bits)."""
    if total_carrier_bits <= 0:
        return 0.0
    payload_bits = payload_bytes * 8 + 32  # include 32-bit length header
    return min(1.0, max(0.0, payload_bits / total_carrier_bits))


def check_capacity(image: Image.Image, payload_length_bytes: int) -> None:
    """Verify that the carrier image has enough capacity for the payload.
    
    Raises:
        CapacityExceededError: If payload cannot fit in the image carrier.
    """
    cap = calculate_image_capacity(image)
    if payload_length_bytes > cap["max_payload_bytes"]:
        raise CapacityExceededError(
            f"Payload of {payload_length_bytes} bytes exceeds carrier capacity of "
            f"{cap['max_payload_bytes']} bytes ({cap['width']}x{cap['height']} image)."
        )

