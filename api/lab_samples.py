"""Evaluation Lab live sample run: hide a payload in each built-in sample and show what it is exposed to.

The samples are held-out DIV2K crops bundled in api/samples/ (see manifest.json). For one sample
and one payload share, each embedding algorithm gets: the pre-flight prediction, the detector's
score on a real encrypted stego image, visual quality, and a map of exactly which values changed.
"""

from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from api.errors import ApiError
from api.schemas import (
    EmbeddingAlgorithmChoice,
    LabSample,
    LabSampleRunResponse,
    LabSamplesResponse,
    RiskLevel,
    SampleAlgorithmResult,
    SampleTexture,
)
from core.crypto import MODE_ASYMMETRIC, packet_overhead
from core.keys import generate_keypair
from core.pipeline import max_message_bytes, stego_encode_asymmetric
from experiments.common import seeded_bytes, seeded_key
from experiments.quality import measure_quality
from ml.dataset import DEFAULT_SEED
from ml.detector import StegoDetector
from ml.risk import PreflightChecker

SAMPLES_DIR = Path(__file__).with_name("samples")
MANIFEST_FILE = SAMPLES_DIR / "manifest.json"
SAMPLE_KEY_MODE = "asymmetric"  # no PBKDF2 per run; the embedded bits look the same in both modes
ALGORITHMS = (EmbeddingAlgorithmChoice.REPLACEMENT, EmbeddingAlgorithmChoice.MATCHING)
PREVIEW_SIZE_PX = 256
PREVIEW_JPEG_QUALITY = 85
CHANGE_MAP_CROP_PX = 128
SLOTS_PER_PIXEL = 3
UNKNOWN_SAMPLE_MESSAGE = "There is no built-in sample with that id."
DETECTOR_UNAVAILABLE_MESSAGE = "The detector isn't installed on this server yet, so the sample run can't score images."


@dataclass(frozen=True)
class Sample:
    """One built-in sample photo."""

    id: str
    title: str
    source_cover_id: str
    texture: SampleTexture
    texture_complexity: float

    @property
    def path(self) -> Path:
        return SAMPLES_DIR / f"{self.id}.png"


@lru_cache(maxsize=1)
def load_samples() -> tuple[Sample, ...]:
    """The samples listed in manifest.json, in display order (smooth to textured)."""
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return tuple(
        Sample(
            id=entry["id"],
            title=entry["title"],
            source_cover_id=entry["source_cover_id"],
            texture=SampleTexture(entry["texture"]),
            texture_complexity=float(entry["texture_complexity"]),
        )
        for entry in manifest["samples"]
    )


@lru_cache(maxsize=1)
def samples_source() -> str:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))["source"]


def list_samples() -> LabSamplesResponse:
    """Every built-in sample with the URL of its image."""
    return LabSamplesResponse(
        samples=[
            LabSample(
                id=sample.id,
                title=sample.title,
                texture=sample.texture,
                texture_complexity=sample.texture_complexity,
                image_url=f"/api/lab/samples/{sample.id}/image",
            )
            for sample in load_samples()
        ],
        source=samples_source(),
    )


def find_sample(sample_id: str) -> Sample:
    """Look a sample up by id (never by path, so no file outside api/samples can be reached).

    Raises:
        ApiError: The id is not in the manifest (404).
    """
    for sample in load_samples():
        if sample.id == sample_id:
            return sample
    raise ApiError(404, "unknown_sample", UNKNOWN_SAMPLE_MESSAGE)


def run_sample(sample_id: str, payload_percent: float, detector: StegoDetector | None) -> LabSampleRunResponse:
    """Hide `payload_percent` of the sample's capacity with each algorithm and measure the exposure.

    Raises:
        ApiError: Unknown sample (404) or no detector installed (503).
    """
    sample = find_sample(sample_id)
    if detector is None:
        raise ApiError(503, "detector_unavailable", DETECTOR_UNAVAILABLE_MESSAGE)
    cover = _open_rgb(sample.path)
    message_bytes = message_bytes_for_share(cover, payload_percent)
    checker = PreflightChecker(detector, seed=DEFAULT_SEED)
    _, public_key = generate_keypair()
    results = [
        _measure_algorithm(cover, sample, payload_percent, message_bytes, algorithm, checker, detector, public_key)
        for algorithm in ALGORITHMS
    ]
    return LabSampleRunResponse(
        sample_id=sample.id,
        payload_percent=payload_percent,
        message_bytes=message_bytes,
        threshold=detector.threshold,
        results=results,
    )


def message_bytes_for_share(cover: Image.Image, payload_percent: float) -> int:
    """Message size whose encrypted packet fills `payload_percent` of the cover's LSB slots."""
    packet_bytes = int(cover.width * cover.height * SLOTS_PER_PIXEL * payload_percent / 100) // 8
    capacity = max_message_bytes(cover, SAMPLE_KEY_MODE)
    return max(1, min(capacity, packet_bytes - packet_overhead(MODE_ASYMMETRIC)))


def change_map(changed: np.ndarray, crop: int = CHANGE_MAP_CROP_PX) -> Image.Image:
    """Centre crop at full resolution, black where nothing changed; each changed R, G or B value lights its colour.

    A crop rather than a downscale: shrinking would merge neighbouring pixels and make changes look
    several times denser than they are. Here one dot is exactly one changed pixel.
    """
    height, width, _ = changed.shape
    side_y, side_x = min(crop, height), min(crop, width)
    top, left = (height - side_y) // 2, (width - side_x) // 2
    window = changed[top : top + side_y, left : left + side_x]
    return Image.fromarray(window.astype(np.uint8) * 255, "RGB")


def _measure_algorithm(
    cover: Image.Image,
    sample: Sample,
    payload_percent: float,
    message_bytes: int,
    algorithm: EmbeddingAlgorithmChoice,
    checker: PreflightChecker,
    detector: StegoDetector,
    public_key: object,
) -> SampleAlgorithmResult:
    predicted = checker.predict_risk(cover, message_bytes, key_mode=SAMPLE_KEY_MODE, algorithm=algorithm.value)
    message = seeded_bytes(
        seeded_key(DEFAULT_SEED, "lab-sample", sample.id, payload_percent, algorithm.value), message_bytes
    )
    stego = stego_encode_asymmetric(cover, message, public_key, algorithm=algorithm.value)
    probability = min(1.0, max(0.0, detector.predict_probability(stego)))
    quality = measure_quality(cover, stego)
    changed = np.asarray(stego.convert("RGB")) != np.asarray(cover)
    return SampleAlgorithmResult(
        algorithm=algorithm,
        predicted_probability=min(1.0, max(0.0, predicted.probability)),
        predicted_level=RiskLevel(predicted.level.value),
        actual_probability=probability,
        is_detected=probability >= detector.threshold,
        psnr_db=quality.psnr_db if math.isfinite(quality.psnr_db) else None,
        ssim=quality.ssim,
        changed_values=int(changed.sum()),
        changed_share=float(changed.mean()),
        stego_preview=_data_url(_preview(stego), "JPEG"),
        change_map=_data_url(change_map(changed), "PNG"),
    )


def _open_rgb(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        return opened.convert("RGB")


def _preview(image: Image.Image) -> Image.Image:
    preview = image.copy()
    preview.thumbnail((PREVIEW_SIZE_PX, PREVIEW_SIZE_PX))
    return preview


def _data_url(image: Image.Image, image_format: str) -> str:
    buffer = io.BytesIO()
    options = {"quality": PREVIEW_JPEG_QUALITY} if image_format == "JPEG" else {"optimize": True}
    image.save(buffer, format=image_format, **options)
    mime = "image/jpeg" if image_format == "JPEG" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
