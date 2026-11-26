"""Unit tests for the ML modules: features and detector (pre-flight risk is in test_risk.py).

Verifies:
- Feature extraction returns every per-channel and inter-channel feature without NaNs or Infs.
- StegoDetector loads a trained artifact, rejects mismatched ones, and explains its score.
"""

import time

import numpy as np
import pytest
from PIL import Image

from core.embed import embed_payload
from ml.detector import DetectorNotTrainedError, ModelMismatchError, StegoDetector
from ml.features import (
    CHANNEL_FEATURE_NAMES,
    CHANNELS,
    COLOUR_FEATURE_NAMES,
    FEATURE_NAMES,
    extract_features,
    extract_sample_pairs_features,
)
from ml.train_detector import save_artifact


def create_smooth_image(width=128, height=128) -> Image.Image:
    """A smooth RGB gradient (little texture)."""
    x = np.linspace(50, 150, width, dtype=np.uint8)
    y = np.linspace(50, 150, height, dtype=np.uint8)
    xx, yy = np.meshgrid(x, y)
    arr = np.stack([xx, yy, ((xx.astype(int) + yy.astype(int)) // 2).astype(np.uint8)], axis=-1)
    return Image.fromarray(arr)


def create_photo_like_image(size=128, seed=5) -> Image.Image:
    """Smooth scene plus mild noise shared by all channels, like a demosaiced camera photo."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 6, size)
    scene = 120 + 50 * np.sin(x)[None, :] * np.cos(x)[:, None]
    shared_noise = rng.normal(0, 1.5, size=(size, size))
    channels = [scene + shared_noise + offset for offset in (8, 0, -10)]
    return Image.fromarray(np.clip(np.stack(channels, axis=-1), 0, 255).round().astype(np.uint8))


def create_textured_image(width=128, height=128) -> Image.Image:
    """Uniform random RGB noise (maximum texture)."""
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


def test_detector_predicts_probability_and_top_features(tiny_model_path):
    detector = StegoDetector(tiny_model_path)
    result = detector.predict(create_textured_image(128, 128))

    assert 0.0 <= result.probability <= 1.0
    assert result.is_stego == (result.probability >= result.threshold)
    assert len(result.top_features) == 5
    contributions = [c.contribution for c in result.top_features]
    assert contributions == sorted(contributions, reverse=True)
    assert all(c.feature in FEATURE_NAMES for c in result.top_features)


def test_detector_predicts_512px_image_in_under_one_second(tiny_model_path):
    detector = StegoDetector(tiny_model_path)
    image = create_textured_image(512, 512)
    start = time.perf_counter()
    detector.predict(image)
    assert time.perf_counter() - start < 1.0


def test_detector_decides_with_the_threshold_stored_in_its_artifact(tiny_artifact, tmp_path):
    path = tmp_path / "detector.joblib"
    save_artifact(tiny_artifact | {"decision_threshold": 0.9}, path)

    result = StegoDetector(path).predict(create_textured_image(64, 64))

    assert result.threshold == 0.9
    assert result.is_stego == (result.probability >= 0.9)


def test_missing_model_raises_not_trained_error(tmp_path):
    with pytest.raises(DetectorNotTrainedError, match="python -m ml.train_detector"):
        StegoDetector(tmp_path / "absent.joblib")


def test_model_with_different_feature_names_is_rejected(tiny_artifact, tmp_path):
    stale = tiny_artifact | {"feature_names": [*FEATURE_NAMES[:-1], "renamed_feature_b"]}
    path = tmp_path / "stale.joblib"
    save_artifact(stale, path)
    with pytest.raises(ModelMismatchError, match="different feature set"):
        StegoDetector(path)


def test_model_with_unknown_artifact_version_is_rejected(tiny_artifact, tmp_path):
    path = tmp_path / "future.joblib"
    save_artifact(tiny_artifact | {"format_version": 99}, path)
    with pytest.raises(ModelMismatchError):
        StegoDetector(path)


def test_feature_names_are_per_channel_then_inter_channel():
    assert len(FEATURE_NAMES) == len(CHANNEL_FEATURE_NAMES) * len(CHANNELS) + len(COLOUR_FEATURE_NAMES)
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    assert FEATURE_NAMES[0] == f"{CHANNEL_FEATURE_NAMES[0]}_r"
    assert FEATURE_NAMES[-len(COLOUR_FEATURE_NAMES) :] == COLOUR_FEATURE_NAMES


def test_grey_image_has_flat_channel_difference_planes():
    _, features = extract_features(create_smooth_image(64, 64).convert("L"))

    assert features["colour_rg_h_zero"] == 1.0
    assert features["colour_gb_v_one"] == 0.0


def test_colour_cooccurrence_shares_sum_to_one():
    _, features = extract_features(create_photo_like_image())

    shares = [value for name, value in features.items() if name.startswith("colour_rg_h_cooc_")]
    assert sum(shares) == pytest.approx(1.0)


def test_lsb_matching_roughens_channel_difference_planes():
    """+/-1 embedding is independent per channel, so it breaks the cross-channel noise correlation."""
    cover = create_photo_like_image()
    payload = np.random.default_rng(1).bytes(cover.width * cover.height * 3 // 16)
    stego = embed_payload(cover, payload, perm_key=b"k" * 32, mode="pseudorandom", algorithm="matching")

    _, clean = extract_features(cover)
    _, embedded = extract_features(stego)

    assert embedded["colour_rg_h_zero"] < clean["colour_rg_h_zero"]
    assert embedded["colour_corr_h_rg"] < clean["colour_corr_h_rg"]


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


def test_sample_pairs_estimate_tracks_lsb_replacement_rate():
    """SPA should read ~0 on a natural-looking cover and ~the true rate after LSB replacement."""
    rng = np.random.default_rng(3)
    smooth = np.cumsum(rng.normal(0, 2, size=(256, 256)), axis=1) + np.linspace(60, 180, 256)[:, None]
    plane = np.clip(smooth + rng.normal(0, 1.5, size=smooth.shape), 0, 255).astype(np.uint8)
    stego = plane.copy()
    carries_bit = rng.random(plane.shape) < 0.5  # embedding rate 0.5: half the pixels hold a message bit
    stego[carries_bit] = (stego[carries_bit] & 0xFE) | rng.integers(0, 2, size=int(carries_bit.sum()), dtype=np.uint8)

    clean_rate = extract_sample_pairs_features(plane)["spa_rate"]
    stego_rate = extract_sample_pairs_features(stego)["spa_rate"]
    assert abs(clean_rate) < 0.1
    assert abs(stego_rate - 0.5) < 0.1
