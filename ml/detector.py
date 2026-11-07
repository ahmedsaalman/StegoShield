"""StegoShield Defensive AI Steganalysis Detector (Module D & Task L18).

Provides:
- Model loading from joblib files (e.g. models/detector.joblib).
- Feature extraction & probability prediction.
- Explainable AI anomaly breakdown (highlights anomalous statistical features).
- Robust fallback heuristic classifier if no trained .joblib exists yet.
- Training interface using scikit-learn RandomForestClassifier.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from PIL import Image
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier

from ml.features import extract_features, FEATURE_NAMES


DEFAULT_DETECTOR_PATH = Path("models/detector.joblib")


class StegoDetector:
    """Defensive Steganalysis AI Detector."""

    def __init__(self, model_path: Path | str | None = None):
        self.model: Optional[RandomForestClassifier] = None
        self.model_path = Path(model_path) if model_path else DEFAULT_DETECTOR_PATH
        self.is_heuristic = False

        if self.model_path.exists():
            self._load_model(self.model_path)
        else:
            self.is_heuristic = True

    def _load_model(self, path: Path) -> None:
        """Load trained model dictionary from joblib."""
        data = joblib.load(path)
        if isinstance(data, dict) and "model" in data:
            self.model = data["model"]
        elif hasattr(data, "predict_proba"):
            self.model = data
        else:
            raise ValueError(f"Loaded object from {path} does not have a predict_proba method.")
        self.is_heuristic = False

    def train_and_save(
        self,
        X: np.ndarray,
        y: np.ndarray,
        save_path: Path | str | None = None,
        n_estimators: int = 150,
        random_state: int = 42,
    ) -> None:
        """Train a Random Forest classifier and save to joblib."""
        clf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=12,
            min_samples_split=4,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )
        clf.fit(X, y)
        self.model = clf
        self.is_heuristic = False

        target_path = Path(save_path) if save_path else self.model_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": clf, "feature_names": FEATURE_NAMES}, target_path)

    def _heuristic_predict(self, feat_dict: dict[str, float]) -> float:
        """Rule-based statistical heuristic when no ML model is yet loaded.
        
        Evaluates Chi-Square p-value, LSB transition rate, and horizontal difference kurtosis.
        """
        score = 0.0

        # 1. Chi-square attack p-value < 0.01 indicates significant PoV pairing
        p_val = feat_dict.get("chi_square_p_value", 1.0)
        chi_norm = feat_dict.get("chi_square_norm", 0.0)
        if p_val < 0.01:
            score += 0.45
        elif p_val < 0.05:
            score += 0.30

        if chi_norm > 2.0:
            score += 0.20

        # 2. LSB horizontal transition rate in random stego converges to ~0.50
        h_rate = feat_dict.get("lsb_horiz_transition_rate", 0.5)
        # In natural images, h_rate is typically lower (0.25 - 0.42)
        if 0.48 <= h_rate <= 0.52:
            score += 0.30
        elif 0.45 <= h_rate <= 0.55:
            score += 0.15

        # 3. LSB mean deviation from 0.50 (clean images are often 0.40 - 0.60, random stego is 0.495 - 0.505)
        lsb_mean = feat_dict.get("lsb_mean", 0.5)
        if 0.49 <= lsb_mean <= 0.51:
            score += 0.15

        return min(0.99, max(0.01, score))

    def predict_probability(self, image: Image.Image) -> tuple[float, dict[str, float]]:
        """Compute the probability [0.0, 1.0] that the image contains hidden data.
        
        Returns:
            tuple[float, dict[str, float]]: (stego_probability, extracted_features)
        """
        vec, feat_dict = extract_features(image)

        if self.model is not None and not self.is_heuristic:
            # Predict using trained scikit-learn Random Forest
            prob = float(self.model.predict_proba(vec.reshape(1, -1))[0, 1])
        else:
            prob = self._heuristic_predict(feat_dict)

        return prob, feat_dict

    def predict(self, image: Image.Image, threshold: float = 0.50) -> dict[str, Any]:
        """Perform comprehensive steganalysis with explainability breakdown."""
        prob, feat_dict = self.predict_probability(image)
        is_stego = prob >= threshold

        if prob >= 0.85:
            confidence = "High Confidence Stego"
            risk_badge = "🔴 Anomaly Detected"
        elif prob >= threshold:
            confidence = "Moderate Confidence Stego"
            risk_badge = "🟠 Suspicious"
        elif prob >= 0.25:
            confidence = "Likely Clean"
            risk_badge = "🟡 Low Probability"
        else:
            confidence = "High Confidence Clean"
            risk_badge = "🟢 Clean Carrier"

        # Highlight key contributing indicators
        anomalies = []
        if feat_dict.get("chi_square_p_value", 1.0) < 0.05:
            anomalies.append({
                "metric": "Chi-Square Test",
                "finding": "Asymmetric Pair-of-Values (PoV) distribution detected",
                "p_value": f"{feat_dict['chi_square_p_value']:.4e}",
            })
        if 0.47 <= feat_dict.get("lsb_horiz_transition_rate", 0.0) <= 0.53:
            anomalies.append({
                "metric": "LSB Spatial Autocorrelation",
                "finding": "Near-random horizontal bit transition rate (~50%)",
                "rate": f"{feat_dict['lsb_horiz_transition_rate']:.3f}",
            })
        if 0.49 <= feat_dict.get("lsb_mean", 0.0) <= 0.51:
            anomalies.append({
                "metric": "LSB Bit-Plane Uniformity",
                "finding": "LSB mean is balanced close to 0.500 (typical of ciphertext)",
                "mean": f"{feat_dict['lsb_mean']:.3f}",
            })

        return {
            "is_stego": is_stego,
            "probability": prob,
            "probability_percent": f"{prob * 100:.1f}%",
            "confidence": confidence,
            "badge": risk_badge,
            "threshold": threshold,
            "model_type": "Trained Random Forest" if (self.model and not self.is_heuristic) else "Statistical Heuristic Baseline",
            "features": feat_dict,
            "anomalies": anomalies,
        }

