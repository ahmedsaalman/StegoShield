"""Unit tests for StegoShield Machine Learning Modules (Tasks L16, L18, L19).

Verifies:
- Feature extraction returns all 27 defined features without NaNs or Infs.
- StegoDetector runs inference, bounds probabilities [0.0, 1.0], and produces anomaly breakdowns.
- PreFlightRiskScorer correctly scores smooth vs textured images.
- Dataset generator creates paired records without errors.
"""

import pytest
import numpy as np
from PIL import Image

from ml.features import extract_features, FEATURE_NAMES
from ml.detector import StegoDetector
from ml.risk import PreFlightRiskScorer
from ml.dataset import generate_synthetic_covers, generate_stego_samples_for_cover


def create_smooth_image(width=128, height=128) -> Image.Image:
    """Create a very smooth gradient image (should have low texture, high risk)."""
    x = np.linspace(50, 150, width, dtype=np.uint8)
    y = np.linspace(50, 150, height, dtype=np.uint8)
    xx, yy = np.meshgrid(x, y)
    arr = np.stack([xx, yy, ((xx.astype(int) + yy.astype(int)) // 2).astype(np.uint8)], axis=-1)
    return Image.fromarray(arr, mode="RGB")


def create_textured_image(width=128, height=128) -> Image.Image:
    """Create a noisy / high-texture image (should have high texture, lower risk)."""
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def test_feature_extraction_completeness_and_validity():
    """Verify that extract_features returns all 27 defined features with valid numbers."""
    img = create_smooth_image(100, 100)
    vec, feat_dict = extract_features(img)

    assert len(vec) == len(FEATURE_NAMES)
    assert len(feat_dict) == len(FEATURE_NAMES)
    assert not np.isnan(vec).any()
    assert not np.isinf(vec).any()

    # All expected keys must be present
    for name in FEATURE_NAMES:
        assert name in feat_dict
        assert isinstance(feat_dict[name], (int, float))


def test_stego_detector_inference():
    """Verify StegoDetector inference and response structure."""
    detector = StegoDetector()
    img = create_smooth_image(128, 128)

    result = detector.predict(img)
    assert "probability" in result
    assert 0.0 <= result["probability"] <= 1.0
    assert "is_stego" in result
    assert "confidence" in result
    assert "badge" in result
    assert "anomalies" in result
    assert isinstance(result["features"], dict)


def test_preflight_risk_scorer_differentiation():
    """Verify that textured images receive lower detectability risk than smooth images."""
    scorer = PreFlightRiskScorer()
    smooth_img = create_smooth_image(128, 128)
    textured_img = create_textured_image(128, 128)

    smooth_result = scorer.evaluate(smooth_img, target_payload_bytes=100)
    textured_result = scorer.evaluate(textured_img, target_payload_bytes=100)

    assert 0.0 <= smooth_result["risk_score"] <= 1.0
    assert 0.0 <= textured_result["risk_score"] <= 1.0
    assert smooth_result["risk_level"] in ("Low", "Medium", "High")
    assert textured_result["risk_level"] in ("Low", "Medium", "High")

    # Smooth image must have higher detectability risk than a heavily textured image
    assert smooth_result["risk_score"] > textured_result["risk_score"]


def test_dataset_generator_sample(tmp_path):
    """Verify that dataset generator creates valid sample records."""
    covers = generate_synthetic_covers(tmp_path, count=2, size=(64, 64))
    assert len(covers) == 2

    records = generate_stego_samples_for_cover(
        covers[0],
        payload_ratios=[0.05, 0.10],
        modes=["pseudorandom"],
        algorithms=["replacement"],
    )
    # 1 clean + 2 stego = 3 records
    assert len(records) == 3
    assert records[0]["is_stego"] == 0
    assert records[1]["is_stego"] == 1
    assert records[2]["is_stego"] == 1

