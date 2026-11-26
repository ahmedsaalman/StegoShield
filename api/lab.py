"""Adapter from experiments/ to the Evaluation Lab endpoints.

The only API module that knows the shape of experiments/ results. The live demos
call the same functions as the batch scripts (no duplicated logic), on the
uploaded image instead of a held-out cover. Nothing is stored.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd
from PIL import Image

from api.errors import ApiError
from api.schemas import (
    AttackTrial,
    DetectorPoint,
    LabAttacksResponse,
    LabDetectorComparisonResponse,
    LabOutcome,
    LabQualityResponse,
    LabResultsResponse,
    LabRobustnessResponse,
    PreflightValidityRow,
    QualityPoint,
    QualityRow,
    RobustnessRow,
    SliceAuc,
    TransportTrial,
)
from experiments.attacks import ATTACK_DESCRIPTIONS, run_all_attacks
from experiments.common import RESULTS_DIR
from experiments.detector_eval import score_payload_variants
from experiments.quality import quality_grid
from experiments.robustness import MESSAGE_BYTES, TRANSPORT_LABELS, Transport, robustness_grid
from ml.dataset import DEFAULT_SEED
from ml.detector import StegoDetector

# Each demo embeds the image many times (the detector comparison scores it 9 times), so
# uploads are capped well below the general limit; 512 x 512 is the size the detector knows.
LAB_MAX_PIXELS = 1024 * 1024
LAB_LABEL = "upload"
LIVE_KEY_MODES = ("asymmetric",)  # password mode behaves the same and costs a PBKDF2 run per trial
RESULT_FILES = ("detector_metrics", "preflight_eval_summary", "robustness_summary", "quality_summary", "split")
DETECTOR_UNAVAILABLE_MESSAGE = "The detector isn't installed on this server yet, so this comparison can't run."
RESULTS_UNAVAILABLE_MESSAGE = (
    "The saved experiment results aren't on this server. Run the experiments/ scripts to create them."
)


def lab_quality(image: Image.Image) -> LabQualityResponse:
    """PSNR and SSIM of the image with test data at every payload share and algorithm.

    Raises:
        ApiError: The image is larger than the Lab's pixel limit (413).
    """
    rows = quality_grid(_lab_image(image), DEFAULT_SEED, label=LAB_LABEL)
    return LabQualityResponse(
        points=[
            QualityPoint(
                algorithm=row["algorithm"],
                payload_percent=_percent(row["ratio"]),
                psnr_db=row["psnr_db"] if math.isfinite(row["psnr_db"]) else None,
                ssim=row["ssim"],
            )
            for row in rows
        ]
    )


def lab_robustness(image: Image.Image) -> LabRobustnessResponse:
    """Hide a real message, send it through each transport, and report whether it survived.

    Raises:
        ApiError: The image is larger than the Lab's pixel limit (413).
    """
    rows = robustness_grid(_lab_image(image), DEFAULT_SEED, label=LAB_LABEL, key_modes=LIVE_KEY_MODES)
    return LabRobustnessResponse(
        message_bytes=MESSAGE_BYTES,
        trials=[
            TransportTrial(
                transport=row["transport"],
                label=TRANSPORT_LABELS[Transport(row["transport"])],
                outcome=LabOutcome(row["outcome"]),
            )
            for row in rows
        ],
    )


def lab_attacks(image: Image.Image) -> LabAttacksResponse:
    """Run every attack demo against fresh stego images made from the upload.

    Raises:
        ApiError: The image is larger than the Lab's pixel limit (413).
    """
    results = run_all_attacks(_lab_image(image), DEFAULT_SEED, label=LAB_LABEL)
    return LabAttacksResponse(
        trials=[
            AttackTrial(
                attack=result.attack.value,
                description=ATTACK_DESCRIPTIONS[result.attack],
                outcome=LabOutcome(result.outcome.value),
            )
            for result in results
        ]
    )


def lab_detector_comparison(image: Image.Image, detector: StegoDetector | None) -> LabDetectorComparisonResponse:
    """Detector score for the clean upload and for test data at every payload share and algorithm.

    Raises:
        ApiError: No detector is installed (503) or the image is too large (413).
    """
    if detector is None:
        raise ApiError(503, "detector_unavailable", DETECTOR_UNAVAILABLE_MESSAGE)
    cover = _lab_image(image)
    rows = score_payload_variants(cover, detector, DEFAULT_SEED, label=LAB_LABEL)
    return LabDetectorComparisonResponse(
        clean_probability=_probability(detector.predict_probability(cover)),
        threshold=detector.threshold,
        points=[
            DetectorPoint(
                algorithm=row["algorithm"],
                payload_percent=_percent(row["ratio"]),
                probability=_probability(row["probability"]),
                is_detected=row["probability"] >= detector.threshold,
            )
            for row in rows
        ],
    )


def lab_results(results_dir: Path = RESULTS_DIR) -> LabResultsResponse:
    """Headline numbers from the saved held-out experiment runs (see docs/results.md).

    Raises:
        ApiError: The results files are missing (503).
    """
    return _load_results(results_dir)


@lru_cache(maxsize=4)
def _load_results(results_dir: Path) -> LabResultsResponse:
    paths = {name: results_dir / f"{name}.csv" for name in RESULT_FILES}
    if not all(path.exists() for path in paths.values()):
        raise ApiError(503, "lab_results_unavailable", RESULTS_UNAVAILABLE_MESSAGE)
    tables = {name: pd.read_csv(path, dtype={"cover_id": str}) for name, path in paths.items()}
    detector = tables["detector_metrics"]
    split = tables["split"]
    return LabResultsResponse(
        seed=int(detector["seed"].iloc[0]),
        held_out_covers=int((split["side"] == "test").sum()),
        detector=[
            SliceAuc(
                algorithm=row.algorithm,
                layout=row.layout,
                payload_percent=_percent(float(row.ratio)),
                roc_auc=row.roc_auc,
            )
            for row in detector[detector["ratio"] != "all"].itertuples()
        ],
        preflight_validity=[
            PreflightValidityRow(
                texture=row.texture,
                predicted_level=row.predicted_level,
                n_trials=row.n_trials,
                actual_detection_rate=row.actual_detection_rate,
            )
            for row in tables["preflight_eval_summary"].itertuples()
        ],
        robustness=[
            RobustnessRow(
                transport=row.transport,
                label=TRANSPORT_LABELS[Transport(row.transport)],
                n_trials=row.n_trials,
                recovered_rate=row.recovered_rate,
                failed_safely_rate=row.failed_safely_rate,
                unsafe_rate=row.unsafe_rate,
            )
            for row in tables["robustness_summary"].itertuples()
        ],
        quality=[
            QualityRow(
                algorithm=row.algorithm,
                payload_percent=_percent(row.ratio),
                psnr_mean_db=row.psnr_mean,
                ssim_mean=row.ssim_mean,
            )
            for row in tables["quality_summary"].itertuples()
        ],
    )


def _lab_image(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width * height > LAB_MAX_PIXELS:
        raise ApiError(
            413,
            "image_too_large",
            f"The image is {width}×{height} pixels. Evaluation Lab demos accept up to {LAB_MAX_PIXELS:,} "
            "pixels (for example 1024×1024), because each demo processes the image many times. "
            "Crop or resize it first.",
            field="image",
        )
    return image.convert("RGB")


def _percent(ratio: float) -> float:
    return round(ratio * 100, 3)


def _probability(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
