"""Shared fixtures: fast password key derivation, a small synthetic feature table and a tiny trained detector."""

import numpy as np
import pandas as pd
import pytest

from core import crypto
from ml.dataset import DEFAULT_VARIANTS, META_COLUMNS
from ml.features import FEATURE_NAMES
from ml.train_detector import save_artifact, split_by_source, train_detector

FAST_FOREST = {"n_estimators": 25, "min_samples_leaf": 2, "n_jobs": 1}
FAST_PBKDF2_ITERATIONS = 1_000


@pytest.fixture(autouse=True)
def fast_pbkdf2(request, monkeypatch):
    """Tests check what password key derivation does, not what it costs.

    1,000 PBKDF2 rounds instead of 600,000 keeps the default run under 10 s. Every password still
    goes through the real PBKDF2 → HKDF chain. Tests marked `real_kdf` keep the production count.
    """
    if request.node.get_closest_marker("real_kdf") is None:
        monkeypatch.setattr(crypto, "PBKDF2_ITERATIONS", FAST_PBKDF2_ITERATIONS)


@pytest.fixture(scope="session")
def synthetic_table() -> pd.DataFrame:
    """30 sources x 2 crops; stego rows shift a few features in proportion to the payload ratio."""
    rng = np.random.default_rng(0)
    rows = []
    for source in range(30):
        for crop in range(2):
            base = {"cover_id": f"{source:04d}_{crop}", "source_id": f"{source:04d}", "seed": 0}
            rows.append(base | {"label": 0, "ratio": 0.0, "layout": "none", "algorithm": "none"})
            for v in DEFAULT_VARIANTS:
                rows.append(base | {"label": 1, "ratio": v.ratio, "layout": v.layout, "algorithm": v.algorithm})
    table = pd.DataFrame(rows, columns=META_COLUMNS)
    features = rng.normal(size=(len(table), len(FEATURE_NAMES)))
    features[:, :5] += 4 * table["ratio"].to_numpy()[:, None] + 1.5 * table["label"].to_numpy()[:, None]
    return pd.concat([table, pd.DataFrame(features, columns=FEATURE_NAMES)], axis=1)


@pytest.fixture(scope="session")
def tiny_artifact(synthetic_table) -> dict:
    """A detector artifact trained on the synthetic table (fast forest, seed 1)."""
    return train_detector(split_by_source(synthetic_table, seed=1).train, seed=1, forest_params=FAST_FOREST)


@pytest.fixture(scope="session")
def tiny_model_path(tiny_artifact, tmp_path_factory):
    """The tiny artifact saved as a joblib file."""
    path = tmp_path_factory.mktemp("models") / "detector.joblib"
    save_artifact(tiny_artifact, path)
    return path
