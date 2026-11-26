"""Tests for detector training (ml/train_detector.py) on a small synthetic feature table."""

import pandas as pd
import pytest

from ml.dataset import DEFAULT_VARIANTS
from ml.features import FEATURE_NAMES
from ml.train_detector import (
    CALIBRATION_METHODS,
    balanced_sample_weights,
    evaluate_detector,
    split_by_source,
)


@pytest.fixture(scope="module")
def trained(synthetic_table, tiny_artifact):
    split = split_by_source(synthetic_table, seed=1)
    return split, tiny_artifact, evaluate_detector(tiny_artifact, split.test)


def test_split_keeps_each_source_photo_on_one_side(synthetic_table):
    split = split_by_source(synthetic_table, seed=1)
    assert set(split.train["source_id"]).isdisjoint(split.test["source_id"])
    assert set(split.train["cover_id"]).isdisjoint(split.test["cover_id"])
    assert len(split.train) + len(split.test) == len(synthetic_table)


def test_split_is_reproducible(synthetic_table):
    a, b = split_by_source(synthetic_table, seed=4), split_by_source(synthetic_table, seed=4)
    assert a.test["cover_id"].tolist() == b.test["cover_id"].tolist()


def test_balanced_weights_give_classes_equal_total_weight():
    labels = pd.Series([0] * 2 + [1] * 32)
    weights = balanced_sample_weights(labels)
    assert weights[labels == 0].sum() == pytest.approx(weights[labels == 1].sum())


def test_artifact_records_how_it_was_trained(trained):
    _, artifact, _ = trained
    assert artifact["feature_names"] == FEATURE_NAMES
    assert artifact["calibration_method"] in CALIBRATION_METHODS
    assert artifact["seed"] == 1
    assert len(artifact["feature_importances"]) == len(FEATURE_NAMES)


def test_metrics_cover_every_slice_and_separate_easy_signal(trained):
    _, _, metrics = trained
    assert metrics["overall"]["roc_auc"] > 0.9
    for v in DEFAULT_VARIANTS:
        combo = f"ratio={v.ratio}|layout={v.layout}|algorithm={v.algorithm}"
        assert 0.0 <= metrics["per_slice"][combo]["roc_auc"] <= 1.0
    assert "ratio=0.5" in metrics["per_slice"] and "layout=sequential" in metrics["per_slice"]
    assert len(metrics["top_feature_importances"]) == 15


def test_calibrated_probabilities_are_valid(trained):
    split, artifact, _ = trained
    probabilities = artifact["model"].predict_proba(split.test[FEATURE_NAMES].to_numpy())[:, 1]
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
