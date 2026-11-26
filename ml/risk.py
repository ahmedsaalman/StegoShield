"""Pre-flight check (Module B): exact capacity, detector-in-the-loop risk, safe payload size.

The risk is not a formula. A copy of the cover gets seeded random bytes of the
planned size, embedded the way the real pipeline embeds (pseudorandom slots,
chosen algorithm), and the trained detector scores that copy. An encrypted
message is indistinguishable from random bytes, so this is the score an analyst
running the detector would see on the real stego image.

There is no fallback: without a trained detector, loading fails with the
detector's own error, so the UI can say why the check is unavailable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from core.capacity import CapacityExceededError
from core.crypto import MODE_ASYMMETRIC, MODE_PASSWORD, packet_overhead
from core.embed import EmbeddingAlgorithm, embed_payload
from ml.dataset import LENGTH_PREFIX_BYTES, PAYLOAD_RATIOS
from ml.detector import DEFAULT_DETECTOR_PATH, StegoDetector
from ml.features import extract_complexity_features

RISK_LOW_BELOW = 0.35
RISK_HIGH_ABOVE = 0.65
DEFAULT_SIMULATION_SEED = 2026
SLOTS_PER_PIXEL = 3  # R, G and B; alpha is never touched
PACKET_MODES = {"password": MODE_PASSWORD, "asymmetric": MODE_ASYMMETRIC}


class RiskLevel(StrEnum):
    """How likely the detector is to flag the stego image."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProbabilityModel(Protocol):
    """Anything that scores an image with P(stego); StegoDetector in production."""

    def predict_probability(self, image: Image.Image) -> float: ...


@dataclass(frozen=True)
class RatioRisk:
    """Simulated detection risk if the message filled one standard share of the cover."""

    ratio: float
    message_bytes: int
    probability: float
    level: RiskLevel


@dataclass(frozen=True)
class PreflightResult:
    """Everything the sender needs to decide before hiding a message."""

    capacity_bytes: int
    planned_message_bytes: int
    planned_ratio: float
    risk_probability: float
    risk_level: RiskLevel
    recommended_max_bytes: int
    ratio_risks: tuple[RatioRisk, ...]
    texture_complexity: float

    @property
    def is_cover_recommended(self) -> bool:
        """False when neither the planned size nor any standard payload share is Low risk."""
        return self.recommended_max_bytes > 0


def classify_risk(probability: float) -> RiskLevel:
    """Low below 0.35, High above 0.65, Medium in between (both ends inclusive)."""
    if probability < RISK_LOW_BELOW:
        return RiskLevel.LOW
    if probability > RISK_HIGH_ABOVE:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM


class PreflightChecker:
    """Detector-in-the-loop pre-flight check for a planned message."""

    def __init__(self, detector: ProbabilityModel, seed: int = DEFAULT_SIMULATION_SEED) -> None:
        self._detector = detector
        self._seed = seed

    @classmethod
    def load(cls, model_path: Path = DEFAULT_DETECTOR_PATH, seed: int = DEFAULT_SIMULATION_SEED) -> PreflightChecker:
        """Build a checker around the trained detector on disk.

        Raises:
            DetectorNotTrainedError: If no trained model exists.
            ModelMismatchError: If the model doesn't match the current feature extractor.
        """
        return cls(StegoDetector(model_path), seed=seed)

    def check(
        self,
        cover: Image.Image,
        planned_message_bytes: int,
        key_mode: str = "password",
        algorithm: EmbeddingAlgorithm = "replacement",
    ) -> PreflightResult:
        """Capacity, simulated risk for the planned size, and the largest Low-risk size.

        Raises:
            ValueError: If the planned size is negative or the key mode is unknown.
            CapacityExceededError: If the planned message doesn't fit in the cover.
        """
        overhead = _packet_overhead(key_mode)
        if planned_message_bytes < 0:
            raise ValueError("Planned message size can't be negative.")
        rgb = cover.convert("RGB")
        total_slots = rgb.width * rgb.height * SLOTS_PER_PIXEL
        capacity = max(0, total_slots // 8 - overhead)
        if planned_message_bytes > capacity:
            raise CapacityExceededError(
                f"A {planned_message_bytes}-byte message doesn't fit: this cover holds at most "
                f"{capacity} bytes in {key_mode} mode ({rgb.width}x{rgb.height} image)."
            )

        planned_packet_bytes = planned_message_bytes + overhead
        probability = self._simulated_probability(rgb, planned_packet_bytes, algorithm)
        planned_risk = RatioRisk(
            ratio=planned_packet_bytes * 8 / total_slots,
            message_bytes=planned_message_bytes,
            probability=probability,
            level=classify_risk(probability),
        )
        ratio_risks = tuple(self._ratio_risk(rgb, ratio, overhead, capacity, algorithm) for ratio in PAYLOAD_RATIOS)
        return PreflightResult(
            capacity_bytes=capacity,
            planned_message_bytes=planned_message_bytes,
            planned_ratio=planned_risk.ratio,
            risk_probability=probability,
            risk_level=planned_risk.level,
            # The planned size counts too: a Low-risk plan is a safe size even if 5 % is not.
            recommended_max_bytes=_largest_low_risk_bytes((*ratio_risks, planned_risk)),
            ratio_risks=ratio_risks,
            texture_complexity=texture_complexity(rgb),
        )

    def _ratio_risk(
        self, rgb: Image.Image, ratio: float, overhead: int, capacity: int, algorithm: EmbeddingAlgorithm
    ) -> RatioRisk:
        packet_bytes = int(rgb.width * rgb.height * SLOTS_PER_PIXEL * ratio) // 8
        probability = self._simulated_probability(rgb, packet_bytes, algorithm)
        return RatioRisk(
            ratio=ratio,
            message_bytes=min(capacity, max(0, packet_bytes - overhead)),
            probability=probability,
            level=classify_risk(probability),
        )

    def _simulated_probability(self, rgb: Image.Image, packet_bytes: int, algorithm: EmbeddingAlgorithm) -> float:
        # Seeded per (seed, size, algorithm) so the same cover always gets the same answer.
        key = hashlib.sha256(f"{self._seed}|{packet_bytes}|{algorithm}".encode()).digest()
        # embed_payload adds its own 4-byte length prefix, so the total matches the packet size.
        payload = np.random.default_rng(int.from_bytes(key, "big")).bytes(max(1, packet_bytes - LENGTH_PREFIX_BYTES))
        stego = embed_payload(rgb, payload, perm_key=key, mode="pseudorandom", algorithm=algorithm)
        return self._detector.predict_probability(stego)


def texture_complexity(cover: Image.Image) -> float:
    """Laplacian variance of the greyscale cover: higher means more texture to hide changes in."""
    gray = np.asarray(cover.convert("L"))
    return extract_complexity_features(gray)["img_laplacian_var"]


def _packet_overhead(key_mode: str) -> int:
    if key_mode not in PACKET_MODES:
        raise ValueError(f"Unknown key mode {key_mode!r}; expected one of {sorted(PACKET_MODES)}.")
    return packet_overhead(PACKET_MODES[key_mode])


def _largest_low_risk_bytes(ratio_risks: tuple[RatioRisk, ...]) -> int:
    return max((risk.message_bytes for risk in ratio_risks if risk.level is RiskLevel.LOW), default=0)
