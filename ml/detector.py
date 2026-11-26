"""Steganalysis detector (Module D): P(hidden data) for an image, with an explanation.

Loads the calibrated Random Forest artifact written by ml/train_detector.py.
There is deliberately no fallback: if the model is missing or was trained on a
different feature set, loading fails with an error the UI can show.

Explanation: for each feature, contribution = forest importance x how unusual
the value is compared with clean training covers (|z-score|). The top few are
reported as the features that drove this image's score.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from PIL import Image

from ml.features import FEATURE_NAMES, extract_features

DEFAULT_DETECTOR_PATH = Path("models/detector.joblib")
SUPPORTED_ARTIFACT_VERSION = 1
STEGO_THRESHOLD = 0.5
TOP_CONTRIBUTIONS = 5
TRAIN_COMMAND = "python -m ml.train_detector"


class DetectorError(Exception):
    """Base class for detector loading problems."""


class DetectorNotTrainedError(DetectorError):
    """No trained model file exists yet."""


class ModelMismatchError(DetectorError):
    """The model file doesn't match the current feature extractor or artifact format."""


@dataclass(frozen=True)
class FeatureContribution:
    """How much one feature pushed this image's score, and why."""

    feature: str
    value: float
    typical_clean_value: float
    z_score: float
    importance: float
    contribution: float


@dataclass(frozen=True)
class DetectionResult:
    """Detector verdict for one image."""

    probability: float
    threshold: float
    top_features: tuple[FeatureContribution, ...]

    @property
    def is_stego(self) -> bool:
        """True when the probability reaches the decision threshold."""
        return self.probability >= self.threshold


class StegoDetector:
    """Calibrated Random Forest steganalysis detector."""

    def __init__(self, model_path: Path = DEFAULT_DETECTOR_PATH):
        """Load and validate the model artifact.

        Raises:
            DetectorNotTrainedError: If the model file doesn't exist.
            ModelMismatchError: If the artifact's features or format don't match this code.
        """
        artifact = load_detector_artifact(model_path)
        self._model = artifact["model"]
        self._importances = np.asarray(artifact["feature_importances"], dtype=np.float64)
        self._clean_mean = np.asarray(artifact["clean_feature_mean"], dtype=np.float64)
        self._clean_std = np.asarray(artifact["clean_feature_std"], dtype=np.float64)
        self.calibration_method: str = artifact["calibration_method"]
        self.trained_at: str = artifact["trained_at"]

    def predict(self, image: Image.Image, threshold: float = STEGO_THRESHOLD) -> DetectionResult:
        """Probability that the image hides data, plus the features that drove it."""
        vector, _ = extract_features(image)
        return DetectionResult(
            probability=self._probability(vector),
            threshold=threshold,
            top_features=self._top_contributions(vector),
        )

    def predict_probability(self, image: Image.Image) -> float:
        """Probability that the image hides data (calibrated, at equal prior odds)."""
        vector, _ = extract_features(image)
        return self._probability(vector)

    def _probability(self, vector: np.ndarray) -> float:
        return float(self._model.predict_proba(vector.reshape(1, -1))[0, 1])

    def _top_contributions(self, vector: np.ndarray, count: int = TOP_CONTRIBUTIONS) -> tuple[FeatureContribution, ...]:
        z_scores = (vector - self._clean_mean) / self._clean_std
        contributions = self._importances * np.abs(z_scores)
        order = np.argsort(contributions)[::-1][:count]
        return tuple(
            FeatureContribution(
                feature=FEATURE_NAMES[i],
                value=float(vector[i]),
                typical_clean_value=float(self._clean_mean[i]),
                z_score=float(z_scores[i]),
                importance=float(self._importances[i]),
                contribution=float(contributions[i]),
            )
            for i in order
        )


def load_detector_artifact(model_path: Path = DEFAULT_DETECTOR_PATH) -> dict:
    """Load the joblib artifact and check it matches the current feature extractor.

    Raises:
        DetectorNotTrainedError: If the file doesn't exist.
        ModelMismatchError: If feature names or artifact version differ.
    """
    model_path = Path(model_path)
    if not model_path.exists():
        raise DetectorNotTrainedError(f"No trained detector at {model_path}. Train one with `{TRAIN_COMMAND}`.")
    artifact = joblib.load(model_path)
    if not isinstance(artifact, dict) or artifact.get("format_version") != SUPPORTED_ARTIFACT_VERSION:
        raise ModelMismatchError(f"{model_path} is not a version-{SUPPORTED_ARTIFACT_VERSION} detector artifact.")
    if artifact.get("feature_names") != FEATURE_NAMES:
        raise ModelMismatchError(
            f"{model_path} was trained on a different feature set than ml/features.py provides. "
            f"Retrain with `{TRAIN_COMMAND}`."
        )
    return artifact
