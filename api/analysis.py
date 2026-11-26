"""Adapter from the ml/ detector and pre-flight check to API schemas.

This is the only API module that knows the shape of ml/ results, so changes in ml/
only need mirroring here.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from PIL import Image

from api.errors import ApiError
from api.schemas import (
    CapacityResponse,
    DetectionResponse,
    DetectorStatus,
    FeatureContribution,
    KeyMethod,
    MessageCapacity,
    PreflightResponse,
    RiskAssessment,
    RiskLevel,
    Verdict,
)
from core.capacity import calculate_image_capacity
from core.crypto import MODE_ASYMMETRIC, MODE_PASSWORD, packet_overhead
from core.embed import EmbeddingAlgorithm
from core.pipeline import max_message_bytes
from ml.detector import DEFAULT_DETECTOR_PATH, DetectionResult, DetectorError, StegoDetector
from ml.risk import PreflightChecker, PreflightResult
from ml.risk import RiskLevel as SimulatedRiskLevel

logger = logging.getLogger("stegoshield.api")

DETECTOR_MODEL_TYPE = "Calibrated Random Forest"
DETECTOR_UNAVAILABLE_MODEL_TYPE = "Not installed"
# Verdict bands around the detector's own decision threshold; display wording only.
CLEAN_BELOW_PROBABILITY = 0.25
STEGO_FROM_PROBABILITY = 0.85
# The Hide endpoint embeds with LSB matching by default, so the pre-flight simulates that.
SIMULATED_ALGORITHM: EmbeddingAlgorithm = "matching"
# Laplacian-variance bands for the texture label; display wording only, not part of the risk.
HIGH_TEXTURE_FROM = 300.0
MODERATE_TEXTURE_FROM = 80.0
DETECTOR_UNAVAILABLE_MESSAGE = "The detector isn't installed on this server yet, so images can't be scanned."
PREFLIGHT_UNAVAILABLE_MESSAGE = (
    "The detector isn't installed on this server yet, so detection risk can't be estimated. "
    "Capacity is still shown when you choose an image."
)

_PIPELINE_MODE_NAMES = {KeyMethod.PASSWORD: "password", KeyMethod.PUBLIC_KEY: "asymmetric"}
_PACKET_MODES = {KeyMethod.PASSWORD: MODE_PASSWORD, KeyMethod.PUBLIC_KEY: MODE_ASYMMETRIC}


def describe_capacity(image: Image.Image, is_lossy_source: bool) -> CapacityResponse:
    """Exact message capacity of an image for both protection methods (format v2 overhead included)."""
    return CapacityResponse(
        width=image.width,
        height=image.height,
        channels=calculate_image_capacity(image)["channels"],
        is_lossy_source=is_lossy_source,
        max_message_bytes=MessageCapacity(
            password=max_message_bytes(image, _PIPELINE_MODE_NAMES[KeyMethod.PASSWORD]),
            public_key=max_message_bytes(image, _PIPELINE_MODE_NAMES[KeyMethod.PUBLIC_KEY]),
        ),
    )


class AnalysisService:
    """Detection and detector-in-the-loop pre-flight risk; both need the trained detector."""

    def __init__(self, detector: StegoDetector | None, detector_unavailable_reason: str | None = None) -> None:
        self._detector = detector
        self._preflight = PreflightChecker(detector) if detector is not None else None
        self._detector_unavailable_reason = detector_unavailable_reason

    @classmethod
    def load(cls, detector_path: Path | None) -> AnalysisService:
        """Load the detector if one is installed; otherwise record why, so the API can say so."""
        try:
            detector = StegoDetector(detector_path or DEFAULT_DETECTOR_PATH)
        except DetectorError as exc:
            logger.warning("Detector unavailable: %s", exc)
            return cls(None, detector_unavailable_reason=str(exc))
        return cls(detector)

    @property
    def detector(self) -> StegoDetector | None:
        """The loaded detector, or None when it isn't installed."""
        return self._detector

    @property
    def detector_status(self) -> DetectorStatus:
        if self._detector is None:
            return DetectorStatus(
                available=False,
                model_type=DETECTOR_UNAVAILABLE_MODEL_TYPE,
                unavailable_reason=self._detector_unavailable_reason,
            )
        return DetectorStatus(available=True, model_type=DETECTOR_MODEL_TYPE, trained_at=self._detector.trained_at)

    def detect(self, image: Image.Image) -> DetectionResponse:
        """Probability that the image hides data, with the features that drove it.

        Raises:
            ApiError: No trained detector is installed (503).
        """
        if self._detector is None:
            raise ApiError(503, "detector_unavailable", DETECTOR_UNAVAILABLE_MESSAGE)
        result = self._detector.predict(image.convert("RGB"))
        return DetectionResponse(
            probability=_clamp_probability(result.probability),
            verdict=_verdict_for(result),
            is_stego=result.is_stego,
            threshold=result.threshold,
            model_type=DETECTOR_MODEL_TYPE,
            top_features=[_to_contribution(item) for item in result.top_features if _is_finite(item)],
        )

    def preflight(
        self, image: Image.Image, message_bytes: int, method: KeyMethod, is_lossy_source: bool
    ) -> PreflightResponse:
        """Capacity, simulated detection risk and the largest low-risk size for a planned message.

        A message that doesn't fit is reported with fits=False and the risk of filling the image.

        Raises:
            ApiError: No trained detector is installed (503).
            CapacityExceededError: The image can't hold even an empty message.
        """
        if self._preflight is None:
            raise ApiError(503, "detector_unavailable", PREFLIGHT_UNAVAILABLE_MESSAGE)
        capacity = describe_capacity(image, is_lossy_source)
        method_capacity: int = getattr(capacity.max_message_bytes, method.value)
        fits = message_bytes <= method_capacity
        simulated_bytes = message_bytes if fits else method_capacity
        result = self._preflight.check(
            image, simulated_bytes, key_mode=_PIPELINE_MODE_NAMES[method], algorithm=SIMULATED_ALGORITHM
        )
        packet_bits = (message_bytes + packet_overhead(_PACKET_MODES[method])) * 8
        total_slots = calculate_image_capacity(image)["total_carrier_bits"]
        return PreflightResponse(
            capacity=capacity,
            message_bytes=message_bytes,
            method=method,
            fits=fits,
            payload_percent=round(100 * packet_bits / total_slots, 3) if total_slots else 100.0,
            recommended_max_message_bytes=min(result.recommended_max_bytes, method_capacity),
            risk=RiskAssessment(
                probability=_clamp_probability(result.risk_probability),
                level=RiskLevel(result.risk_level.value),
                method=_risk_method(simulated_bytes, fits),
            ),
            recommendation=_recommendation(result),
            texture=_texture_label(result.texture_complexity),
        )


def _verdict_for(result: DetectionResult) -> Verdict:
    # The wording never contradicts the detector's own yes/no decision.
    if not result.is_stego:
        return Verdict.LIKELY_CLEAN if result.probability >= CLEAN_BELOW_PROBABILITY else Verdict.CLEAN
    return Verdict.STEGO if result.probability >= STEGO_FROM_PROBABILITY else Verdict.SUSPICIOUS


def _risk_method(simulated_bytes: int, fits: bool) -> str:
    size = f"{simulated_bytes:,}-byte" if fits else "full-capacity"
    return (
        f"Simulated: the trained detector scored a copy of this image with a {size} test message hidden by LSB matching"
    )


def _recommendation(result: PreflightResult) -> str:
    if not result.is_cover_recommended:
        return (
            "Even small messages in this image are likely to be noticed. "
            "Choose a different image; larger photos with natural detail work best."
        )
    limit = f"{result.recommended_max_bytes:,} bytes"
    if result.risk_level is SimulatedRiskLevel.LOW:
        return f"A message this size is unlikely to be noticed. Stay at or under {limit} to keep the risk low."
    return f"Shorten the message to {limit} or less to bring the risk down to low, or choose a larger image."


def _texture_label(laplacian_variance: float) -> str:
    if laplacian_variance >= HIGH_TEXTURE_FROM:
        return "Highly textured"
    if laplacian_variance >= MODERATE_TEXTURE_FROM:
        return "Moderately textured"
    return "Smooth"


def _to_contribution(item: Any) -> FeatureContribution:
    return FeatureContribution(
        feature=item.feature,
        value=item.value,
        typical_clean_value=item.typical_clean_value,
        z_score=item.z_score,
        contribution=item.contribution,
    )


def _is_finite(item: Any) -> bool:
    return all(math.isfinite(v) for v in (item.value, item.typical_clean_value, item.z_score, item.contribution))


def _clamp_probability(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
