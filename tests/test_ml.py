"""Unit tests for the ML modules: features, detector, pre-flight risk.

Verifies:
- Feature extraction returns every per-channel feature without NaNs or Infs.
- StegoDetector runs inference, bounds probabilities [0.0, 1.0], and produces anomaly breakdowns.
- PreFlightRiskScorer correctly scores smooth vs textured images.
"""

import numpy as np
import pytest
from PIL import Image

from ml.detector import StegoDetector
from ml.features import CHANNEL_FEATURE_NAMES, CHANNELS, FEATURE_NAMES, extract_features
from ml.risk import PreFlightRiskScorer


def create_smooth_image(width=128, height=128) -> Image.Image:
    """Create a very smooth gradient image (should have low texture, high risk)."""
    x = np.linspace(50, 150, width, dtype=np.uint8)
    y = np.linspace(50, 150, height, dtype=np.uint8)
    xx, yy = np.meshgrid(x, y)
    arr = np.stack([xx, yy, ((xx.astype(int) + yy.astype(int)) // 2).astype(np.uint8)], axis=-1)
    return Image.fromarray(arr)


def create_textured_image(width=128, height=128) -> Image.Image:
    """Create a noisy / high-texture image (should have high texture, lower risk)."""
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr)


def test_feature_extraction_completeness_and_validity():
    """extract_features returns every feature in FEATURE_NAMES with finite values."""
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


def test_feature_names_are_per_channel():
    assert len(FEATURE_NAMES) == len(CHANNEL_FEATURE_NAMES) * len(CHANNELS)
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    assert FEATURE_NAMES[0] == f"{CHANNEL_FEATURE_NAMES[0]}_r"


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L"])
def test_feature_vector_length_matches_feature_names(mode):
    image = create_textured_image(64, 64).convert(mode)
    vec, feat_dict = extract_features(image)
    assert vec.shape == (len(FEATURE_NAMES),)
    assert list(feat_dict) == FEATURE_NAMES


def test_lsb_change_in_one_channel_only_moves_that_channels_lsb_features():
    """Proves features are per channel: flipping red LSBs must leave green/blue LSB features unchanged."""
    cover = create_smooth_image(96, 96)
    arr = np.array(cover)
    arr[:, :, 0] ^= 1
    _, before = extract_features(cover)
    _, after = extract_features(Image.fromarray(arr))
    assert before["lsb_mean_r"] != after["lsb_mean_r"]
    assert before["lsb_mean_g"] == after["lsb_mean_g"]
    assert before["lsb_mean_b"] == after["lsb_mean_b"]
