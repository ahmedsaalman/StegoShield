"""Adapter from the ml/ detector and pre-flight scorer to API schemas.

This is the only API module that knows the shape of ml/ results, so changes in ml/
(e.g. the Phase 4 detector-in-the-loop pre-flight check) only need mirroring here.
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
from core.pipeline import max_message_bytes
from ml.detector import DEFAULT_DETECTOR_PATH, DetectionResult, DetectorError, StegoDetector
from ml.risk import PreFlightRiskScorer

logger = logging.getLogger("stegoshield.api")

DETECTOR_MODEL_TYPE = "Calibrated Random Forest"
DETECTOR_UNAVAILABLE_MODEL_TYPE = "Not installed"
# Verdict bands around the detector's own decision threshold; display wording only.
CLEAN_BELOW_PROBABILITY = 0.25
STEGO_FROM_PROBABILITY = 0.85

_PIPELINE_MODE_NAMES = {KeyMethod.PASSWORD: "password", KeyMethod.PUBLIC_KEY: "asymmetric"}
_PACKET_MODES = {KeyMethod.PASSWORD: MODE_PASSWORD, KeyMethod.PUBLIC_KEY: MODE_ASYMMETRIC}
_RISK_LEVELS = {"Low": RiskLevel.LOW, "Medium": RiskLevel.MEDIUM, "High": RiskLevel.HIGH}


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
    """Detection and pre-flight risk, backed by whatever ml/ currently provides."""

    def __init__(
        self,
        detector: StegoDetector | None,
        risk_scorer: PreFlightRiskScorer,
        detector_unavailable_reason: str | None = None,
    ) -> None:
        self._detector = detector
        self._risk_scorer = risk_scorer
        self._detector_unavailable_reason = detector_unavailable_reason

    @classmethod
    def load(cls, detector_path: Path | None) -> AnalysisService:
        """Load the detector if one is installed; otherwise record why, so the API can say so."""
        try:
            detector = StegoDetector(detector_path or DEFAULT_DETECTOR_PATH)
        except DetectorError as exc:
            logger.warning("Detector unavailable: %s", exc)
            return cls(None, PreFlightRiskScorer(), detector_unavailable_reason=str(exc))
        return cls(detector, PreFlightRiskScorer())

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
            raise ApiError(
                503,
                "detector_unavailable",
                "The detector isn't installed on this server yet, so images can't be scanned.",
            )
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
        """Capacity, detectability risk and a suggested size limit for a planned message."""
        capacity = describe_capacity(image, is_lossy_source)
        overhead = packet_overhead(_PACKET_MODES[method])
        packet_bytes = message_bytes + overhead
        total_slots = calculate_image_capacity(image)["total_carrier_bits"]
        result = self._risk_scorer.evaluate(image.convert("RGB"), target_payload_bytes=packet_bytes)
        method_capacity: int = getattr(capacity.max_message_bytes, method.value)
        return PreflightResponse(
            capacity=capacity,
            message_bytes=message_bytes,
            method=method,
            fits=message_bytes <= method_capacity,
            payload_percent=round(100 * packet_bytes * 8 / total_slots, 3) if total_slots else 100.0,
            recommended_max_message_bytes=_recommended_bytes(result, overhead, method_capacity),
            risk=RiskAssessment(
                probability=_clamp_probability(result["risk_score"]),
                level=_RISK_LEVELS[result["risk_level"]],
                method=result["model_type"],
            ),
            recommendation=result["recommendation"],
            texture=result["texture_description"],
        )


def _verdict_for(result: DetectionResult) -> Verdict:
    if result.probability >= STEGO_FROM_PROBABILITY:
        return Verdict.STEGO
    if result.is_stego:
        return Verdict.SUSPICIOUS
    if result.probability >= CLEAN_BELOW_PROBABILITY:
        return Verdict.LIKELY_CLEAN
    return Verdict.CLEAN


def _recommended_bytes(risk_result: dict[str, Any], overhead: int, method_capacity: int) -> int:
    safe_packet_bytes = int(risk_result["capacity"]["safe_payload_bytes"])
    return max(0, min(method_capacity, safe_packet_bytes - overhead))


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
