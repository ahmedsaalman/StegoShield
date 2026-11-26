"""Tests for the experiment scripts' building blocks (synthetic images only, no dataset)."""

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from experiments.common import LeakageError, assert_held_out, check_split_is_disjoint, seeded_bytes, seeded_key
from experiments.detector_eval import held_out_rows, roc_for_slice, score_rows, slice_metrics_table
from experiments.preflight_eval import evaluate_cover, label_texture, summarise_by_level
from experiments.quality import quality_at_ratio
from experiments.robustness import Outcome, Transport, apply_transport, transport_trial
from ml.detector import StegoDetector


def photo_like_cover(size: int = 64, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    gradient = np.linspace(40, 200, size)[None, :, None] + rng.normal(0, 6, (size, size, 3))
    return Image.fromarray(np.clip(gradient, 0, 255).astype(np.uint8))


def split_frame(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["cover_id", "source_id", "side"])


# --- common -----------------------------------------------------------------------------------------


def test_seeded_bytes_are_reproducible_and_key_dependent():
    assert seeded_bytes(seeded_key(1, "a"), 32) == seeded_bytes(seeded_key(1, "a"), 32)
    assert seeded_bytes(seeded_key(1, "a"), 32) != seeded_bytes(seeded_key(2, "a"), 32)


def test_split_check_rejects_a_source_photo_on_both_sides():
    split = split_frame([("0801_0", "0801", "train"), ("0801_1", "0801", "test")])

    with pytest.raises(LeakageError, match="source_id"):
        check_split_is_disjoint(split)


def test_assert_held_out_rejects_training_covers(tmp_path):
    split_file = tmp_path / "split.csv"
    split_frame([("0801_0", "0801", "train"), ("0802_0", "0802", "test")]).to_csv(split_file, index=False)

    assert_held_out(["0802_0"], split_file)
    with pytest.raises(LeakageError):
        assert_held_out(["0802_0", "0801_0"], split_file)


# --- quality ----------------------------------------------------------------------------------------


def test_quality_drops_as_payload_grows():
    cover = photo_like_cover()

    small = quality_at_ratio(cover, 0.05, "replacement", seeded_key(0, "q"))
    large = quality_at_ratio(cover, 0.50, "replacement", seeded_key(0, "q"))

    assert small.psnr_db > large.psnr_db > 40
    assert 0 < large.ssim < small.ssim <= 1


# --- robustness -------------------------------------------------------------------------------------


def test_transport_changes_only_what_it_should():
    cover = photo_like_cover()

    assert np.array_equal(np.asarray(apply_transport(cover, Transport.PNG_RESAVE)), np.asarray(cover))
    assert apply_transport(cover, Transport.RESIZE_50).size == (32, 32)


@pytest.mark.parametrize(
    ("transport", "outcome"),
    [(Transport.PNG_RESAVE, Outcome.RECOVERED), (Transport.JPEG_Q90, Outcome.FAILED_SAFELY)],
)
def test_transport_trial_outcomes(transport, outcome):
    assert transport_trial(photo_like_cover(), b"hello", "unused", transport, "asymmetric") is outcome


# --- detector evaluation ----------------------------------------------------------------------------


def test_detector_eval_uses_only_held_out_rows_and_reports_every_slice(synthetic_table, tiny_artifact):
    test = held_out_rows(synthetic_table, seed=1)
    table = slice_metrics_table(tiny_artifact, test)

    train_sources = set(synthetic_table["source_id"]) - set(test["source_id"])
    assert train_sources.isdisjoint(test["source_id"])
    assert len(table) == 1 + 16
    assert table["roc_auc"].between(0, 1).all()


def test_roc_for_slice_spans_zero_to_one(synthetic_table, tiny_artifact):
    scored = score_rows(tiny_artifact, held_out_rows(synthetic_table, seed=1))

    false_positive_rate, true_positive_rate = roc_for_slice(scored, 0.5, "replacement")

    assert false_positive_rate[0] == 0 and false_positive_rate[-1] == 1
    assert true_positive_rate[-1] == 1


# --- pre-flight validity ----------------------------------------------------------------------------


def test_evaluate_cover_pairs_prediction_with_actual_detection(tiny_model_path):
    rows = evaluate_cover(photo_like_cover(size=64), StegoDetector(tiny_model_path), seed=0, cover_id="c")

    assert len(rows) == 2 * 4  # 2 algorithms x 4 payload shares
    assert {row["predicted_level"] for row in rows} <= {"low", "medium", "high"}
    assert all(0 <= row["actual_probability"] <= 1 for row in rows)


def test_evaluate_cover_skips_shares_smaller_than_the_format_overhead(tiny_model_path):
    rows = evaluate_cover(photo_like_cover(size=24), StegoDetector(tiny_model_path), seed=0, cover_id="c")

    assert all(row["message_bytes"] >= 1 for row in rows)
    assert len(rows) < 2 * 4


def test_summary_reports_detection_rate_per_level_and_texture():
    trials = pd.DataFrame(
        {
            "cover_id": ["a", "a", "b", "b"],
            "texture_complexity": [10.0, 10.0, 500.0, 500.0],
            "predicted_level": ["low", "high", "low", "high"],
            "predicted_probability": [0.1, 0.9, 0.2, 0.8],
            "actual_probability": [0.2, 0.9, 0.3, 0.7],
            "detected": [False, True, False, True],
            "seed": [0, 0, 0, 0],
        }
    )

    summary = summarise_by_level(label_texture(trials)).set_index(["texture", "predicted_level"])

    assert summary.loc[("all", "low"), "actual_detection_rate"] == 0
    assert summary.loc[("all", "high"), "n_trials"] == 2
    assert summary.loc[("smooth", "high"), "actual_detection_rate"] == 1
