"""Tests for the detector-in-the-loop pre-flight check (ml/risk.py)."""

import time

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import gaussian_filter

from core.capacity import CapacityExceededError
from core.pipeline import max_message_bytes
from ml.detector import DEFAULT_DETECTOR_PATH, DetectorNotTrainedError
from ml.risk import (
    RISK_HIGH_ABOVE,
    RISK_LOW_BELOW,
    PreflightChecker,
    RiskLevel,
    classify_risk,
    texture_complexity,
)


class ConstantDetector:
    """Scores every image the same, to test the decision logic on its own."""

    def __init__(self, probability: float) -> None:
        self.probability = probability

    def predict_probability(self, image: Image.Image) -> float:
        return self.probability


class ChangedSlotsDetector:
    """P(stego) = 4 x share of slots that differ from the cover; replacement at ratio r scores about 2r."""

    def __init__(self, cover: Image.Image) -> None:
        self.cover = np.asarray(cover.convert("RGB"))

    def predict_probability(self, image: Image.Image) -> float:
        changed = np.mean(np.asarray(image.convert("RGB")) != self.cover)
        return float(min(1.0, 4 * changed))


def noise_cover(size: int = 64, seed: int = 0) -> Image.Image:
    return Image.fromarray(np.random.default_rng(seed).integers(0, 256, (size, size, 3), dtype=np.uint8))


def photo_like_cover(size: int = 128, seed: int = 0) -> Image.Image:
    """Smooth gradients + blurred texture + mild sensor noise: close enough to a photo for the real detector.

    Texture and most of the noise are shared by R, G and B, as in a demosaiced camera photo.
    Fully independent per-channel noise looks like embedding to the inter-channel features.
    """
    rng = np.random.default_rng(seed)
    xx, yy = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size))
    base = np.stack([80 + 90 * xx + 20 * np.sin(9 * yy), 60 + 70 * yy + 15 * np.cos(7 * xx), 100 + 50 * xx * yy], -1)
    shared = gaussian_filter(rng.normal(0, 25, (size, size)), 2) + rng.normal(0, 2, (size, size))
    own_noise = rng.normal(0, 0.4, base.shape)
    return Image.fromarray(np.clip(base + shared[..., None] + own_noise, 0, 255).astype(np.uint8))


@pytest.mark.parametrize(
    ("probability", "level"),
    [
        (0.0, RiskLevel.LOW),
        (RISK_LOW_BELOW - 1e-9, RiskLevel.LOW),
        (RISK_LOW_BELOW, RiskLevel.MEDIUM),
        (RISK_HIGH_ABOVE, RiskLevel.MEDIUM),
        (RISK_HIGH_ABOVE + 1e-9, RiskLevel.HIGH),
        (1.0, RiskLevel.HIGH),
    ],
)
def test_classify_risk_uses_named_thresholds(probability, level):
    assert classify_risk(probability) is level


@pytest.mark.parametrize("key_mode", ["password", "asymmetric"])
def test_capacity_matches_the_pipeline_including_format_overhead(key_mode):
    cover = noise_cover()

    result = PreflightChecker(ConstantDetector(0.1)).check(cover, 10, key_mode=key_mode)

    assert result.capacity_bytes == max_message_bytes(cover, key_mode)


def test_same_cover_and_seed_give_identical_result(tiny_model_path):
    cover = noise_cover()

    first = PreflightChecker.load(tiny_model_path, seed=7).check(cover, 100)
    second = PreflightChecker.load(tiny_model_path, seed=7).check(cover, 100)

    assert first == second


def test_message_larger_than_capacity_raises_with_the_numbers():
    cover = noise_cover(size=16)
    capacity = max_message_bytes(cover, "password")

    with pytest.raises(CapacityExceededError, match=rf"{capacity + 1}-byte.*at most {capacity} bytes"):
        PreflightChecker(ConstantDetector(0.1)).check(cover, capacity + 1)


def test_negative_size_and_unknown_key_mode_are_rejected():
    checker = PreflightChecker(ConstantDetector(0.1))

    with pytest.raises(ValueError, match="negative"):
        checker.check(noise_cover(), -1)
    with pytest.raises(ValueError, match="Unknown key mode"):
        checker.check(noise_cover(), 10, key_mode="rot13")


def test_recommends_the_largest_low_risk_share():
    cover = noise_cover()

    result = PreflightChecker(ChangedSlotsDetector(cover)).check(cover, 10)

    levels = {risk.ratio: risk.level for risk in result.ratio_risks}
    assert levels == {0.05: RiskLevel.LOW, 0.10: RiskLevel.LOW, 0.25: RiskLevel.MEDIUM, 0.50: RiskLevel.HIGH}
    assert result.recommended_max_bytes == next(r.message_bytes for r in result.ratio_risks if r.ratio == 0.10)
    assert result.is_cover_recommended


def test_cover_is_not_recommended_when_nothing_is_low_risk():
    result = PreflightChecker(ConstantDetector(0.9)).check(noise_cover(), 10)

    assert result.risk_level is RiskLevel.HIGH
    assert result.recommended_max_bytes == 0
    assert not result.is_cover_recommended


def test_recommendation_never_exceeds_capacity():
    result = PreflightChecker(ConstantDetector(0.1)).check(noise_cover(size=32), 0)

    assert 0 < result.recommended_max_bytes <= result.capacity_bytes


def test_missing_detector_raises_instead_of_falling_back(tmp_path):
    with pytest.raises(DetectorNotTrainedError):
        PreflightChecker.load(tmp_path / "missing.joblib")


def test_texture_complexity_is_higher_for_textured_cover():
    smooth = Image.new("RGB", (64, 64), (120, 130, 140))

    assert texture_complexity(noise_cover()) > texture_complexity(smooth)


def test_real_detector_risk_rises_with_payload_size():
    """Sanity check on the committed model: 50 % replacement is far easier to detect than 5 %."""
    if not DEFAULT_DETECTOR_PATH.exists():
        pytest.skip("No trained detector committed")

    result = PreflightChecker.load().check(photo_like_cover(), 0)

    risk_by_ratio = {risk.ratio: risk.probability for risk in result.ratio_risks}
    assert risk_by_ratio[0.50] - risk_by_ratio[0.05] > 0.3


@pytest.mark.slow
def test_full_check_on_512px_cover_takes_under_five_seconds():
    if not DEFAULT_DETECTOR_PATH.exists():
        pytest.skip("No trained detector committed")
    checker = PreflightChecker.load()
    cover = photo_like_cover(size=512)

    start = time.perf_counter()
    checker.check(cover, 500)

    assert time.perf_counter() - start < 5.0


def test_predict_risk_matches_the_planned_size_in_a_full_check():
    cover = photo_like_cover()
    checker = PreflightChecker(ChangedSlotsDetector(cover), seed=0)

    single = checker.predict_risk(cover, 300, key_mode="asymmetric", algorithm="matching")
    full = checker.check(cover, 300, key_mode="asymmetric", algorithm="matching")

    assert (single.probability, single.level, single.ratio) == (
        full.risk_probability,
        full.risk_level,
        full.planned_ratio,
    )
