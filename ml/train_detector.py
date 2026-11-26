"""Train the steganalysis detector: calibrated Random Forest on per-channel features.

Steps:
1. Split by source photo (GroupShuffleSplit, 80/20). All crops of one photo, and
   every stego variant of those crops, land on the same side, so nothing leaks.
2. Balance classes with sample weights. Each cover has 1 clean and 16 stego rows,
   so clean rows get weight 16. The calibrated output then reads as P(stego) at
   equal prior odds, which is what the pre-flight risk score needs.
3. Choose the forest's per-split feature share (max_features) by out-of-fold ROC-AUC,
   and sigmoid or isotonic calibration by Brier score, both on grouped validation
   folds inside the training split. The test split is never used for any choice.
4. Fit the final CalibratedClassifierCV (one forest, ensemble=False, to keep the
   artifact small) and report held-out metrics overall and per slice.

Usage:
    python -m ml.train_detector
    python -m ml.train_detector --features data/features/features.csv --seed 2026
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_predict

from ml.features import FEATURE_NAMES

DEFAULT_FEATURES_CSV = Path("data/features/features.csv")
DEFAULT_MODEL_PATH = Path("models/detector.joblib")
DEFAULT_METRICS_PATH = Path("models/detector_metrics.json")
DEFAULT_SEED = 2026

ARTIFACT_FORMAT_VERSION = 1
TEST_SIZE = 0.20
CV_FOLDS = 5
DECISION_THRESHOLD = 0.5
TOP_IMPORTANCES = 15
CALIBRATION_METHODS = ("sigmoid", "isotonic")
SLICE_COLUMNS = ("ratio", "layout", "algorithm")
GROUP_COLUMN = "source_id"
FOREST_PARAMS = {"n_estimators": 300, "min_samples_leaf": 2, "n_jobs": -1}
# With 258 features, "sqrt" samples ~16 per split and can starve strong-but-few features
# (Sample Pairs); larger shares are tried too. Chosen on training folds only.
MAX_FEATURES_CANDIDATES: tuple[str | float, ...] = ("sqrt", 0.2, 0.4)
SELECTION_TREES = 150


@dataclass(frozen=True)
class DataSplit:
    """Train/test partition of the feature table."""

    train: pd.DataFrame
    test: pd.DataFrame


def main() -> None:
    """Command-line entry point."""
    args = _parse_args()
    table = load_feature_table(args.features)
    split = split_by_source(table, seed=args.seed)
    print(f"[*] train {len(split.train)} rows / test {len(split.test)} rows, seed={args.seed}")
    artifact = train_detector(split.train, seed=args.seed)
    metrics = evaluate_detector(artifact, split.test) | {"seed": args.seed, "split": describe_split(split)}
    save_artifact(artifact, args.model)
    _write_json(metrics, args.metrics)
    print(f"[+] calibration={artifact['calibration_method']}  test ROC-AUC={metrics['overall']['roc_auc']:.3f}")
    print(f"[+] Saved {args.model} and {args.metrics}")


def load_feature_table(path: Path) -> pd.DataFrame:
    """Read the feature CSV and check it has every expected feature column.

    Raises:
        ValueError: If feature columns are missing.
    """
    table = pd.read_csv(path)
    missing = [name for name in FEATURE_NAMES if name not in table.columns]
    if missing:
        raise ValueError(f"{path} is missing {len(missing)} feature columns, e.g. {missing[:3]}. Rebuild it.")
    return table


def split_by_source(table: pd.DataFrame, seed: int = DEFAULT_SEED, test_size: float = TEST_SIZE) -> DataSplit:
    """80/20 split where every source photo falls entirely on one side."""
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(table, groups=table[GROUP_COLUMN]))
    return DataSplit(
        train=table.iloc[train_idx].reset_index(drop=True), test=table.iloc[test_idx].reset_index(drop=True)
    )


def balanced_sample_weights(labels: pd.Series) -> np.ndarray:
    """Weights that give both classes the same total weight."""
    counts = labels.value_counts()
    return labels.map(lambda label: len(labels) / (len(counts) * counts[label])).to_numpy(dtype=np.float64)


def train_detector(train: pd.DataFrame, seed: int = DEFAULT_SEED, forest_params: dict | None = None) -> dict:
    """Fit the calibrated forest on the training split and return the model artifact.

    With the default parameters, max_features is chosen by grouped CV on the training split.
    Passing forest_params uses them as given (used by fast tests).
    """
    features, labels = train[FEATURE_NAMES].to_numpy(), train["label"]
    weights = balanced_sample_weights(labels)
    folds = list(GroupKFold(n_splits=CV_FOLDS).split(features, labels, groups=train[GROUP_COLUMN]))
    selection: dict = {}
    if forest_params is None:
        selection = choose_max_features(features, labels.to_numpy(), weights, folds, seed)
        forest_params = FOREST_PARAMS | {"max_features": selection["chosen"]}

    method = choose_calibration_method(features, labels.to_numpy(), weights, folds, _forest(seed, forest_params))
    model = CalibratedClassifierCV(_forest(seed, forest_params), method=method, cv=folds, ensemble=False)
    model.fit(features, labels, sample_weight=weights)

    clean = train.loc[train["label"] == 0, FEATURE_NAMES]
    return {
        "model": model,
        "feature_names": list(FEATURE_NAMES),
        "feature_importances": _forest_of(model).feature_importances_.tolist(),
        "clean_feature_mean": clean.mean().to_numpy().tolist(),
        "clean_feature_std": clean.std().replace(0, 1).to_numpy().tolist(),
        "calibration_method": method,
        "forest_params": {key: value for key, value in forest_params.items() if key != "n_jobs"},
        "max_features_selection": selection,
        "format_version": ARTIFACT_FORMAT_VERSION,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": seed,
    }


def choose_max_features(features: np.ndarray, labels: np.ndarray, weights: np.ndarray, folds: list, seed: int) -> dict:
    """Out-of-fold ROC-AUC on the training split for each max_features candidate, and the best one."""
    scores: dict[str, float] = {}
    for candidate in MAX_FEATURES_CANDIDATES:
        params = FOREST_PARAMS | {"max_features": candidate, "n_estimators": SELECTION_TREES}
        out_of_fold = cross_val_predict(
            _forest(seed, params), features, labels, cv=folds, method="predict_proba", params={"sample_weight": weights}
        )[:, 1]
        scores[str(candidate)] = float(roc_auc_score(labels, out_of_fold, sample_weight=weights))
    best = max(MAX_FEATURES_CANDIDATES, key=lambda candidate: scores[str(candidate)])
    return {"chosen": best, "validation_roc_auc": scores}


def choose_calibration_method(
    features: np.ndarray, labels: np.ndarray, weights: np.ndarray, folds: list, forest: RandomForestClassifier
) -> str:
    """Pick the calibration with the lowest weighted Brier score on out-of-fold forest scores."""
    raw_scores = cross_val_predict(
        forest, features, labels, cv=folds, method="predict_proba", params={"sample_weight": weights}
    )[:, 1]
    briers = {method: _calibrated_brier(method, raw_scores, labels, weights, folds) for method in CALIBRATION_METHODS}
    return min(briers, key=briers.get)


def evaluate_detector(artifact: dict, test: pd.DataFrame) -> dict:
    """Held-out metrics overall, per single slice column, and per full (ratio, layout, algorithm) combination."""
    probabilities = artifact["model"].predict_proba(test[FEATURE_NAMES].to_numpy())[:, 1]
    scored = test.assign(probability=probabilities)
    return {
        "overall": _binary_metrics(scored),
        "per_slice": _slice_metrics(scored),
        "top_feature_importances": top_importances(artifact),
        "calibration_method": artifact["calibration_method"],
        "forest_params": artifact.get("forest_params", {}),
        "max_features_selection": artifact.get("max_features_selection", {}),
        "decision_threshold": DECISION_THRESHOLD,
        "n_test_rows": len(test),
    }


def top_importances(artifact: dict, count: int = TOP_IMPORTANCES) -> list[dict]:
    """The `count` most important features of the forest."""
    order = np.argsort(artifact["feature_importances"])[::-1][:count]
    return [{"feature": artifact["feature_names"][i], "importance": artifact["feature_importances"][i]} for i in order]


def describe_split(split: DataSplit) -> dict:
    """Sizes of the split, for the metrics file."""
    return {
        side: {"rows": len(frame), "covers": frame["cover_id"].nunique(), "sources": frame[GROUP_COLUMN].nunique()}
        for side, frame in (("train", split.train), ("test", split.test))
    }


def save_artifact(artifact: dict, path: Path) -> None:
    """Write the model artifact (compressed joblib)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path, compress=3)


def _forest(seed: int, params: dict) -> RandomForestClassifier:
    return RandomForestClassifier(random_state=seed, **params)


def _forest_of(model: CalibratedClassifierCV) -> RandomForestClassifier:
    return model.calibrated_classifiers_[0].estimator


def _calibrated_brier(method: str, scores: np.ndarray, labels: np.ndarray, weights: np.ndarray, folds: list) -> float:
    calibrated = np.empty_like(scores)
    for fit_idx, eval_idx in folds:
        calibrated[eval_idx] = _fit_and_apply_calibrator(method, scores, labels, weights, fit_idx, eval_idx)
    return float(brier_score_loss(labels, calibrated, sample_weight=weights))


def _fit_and_apply_calibrator(
    method: str,
    scores: np.ndarray,
    labels: np.ndarray,
    weights: np.ndarray,
    fit_idx: np.ndarray,
    eval_idx: np.ndarray,
) -> np.ndarray:
    fit_weights = weights[fit_idx]
    if method == "sigmoid":
        # Platt scaling: an (almost) unregularised logistic fit on the 1-D score
        platt = LogisticRegression(C=1e6).fit(scores[fit_idx, None], labels[fit_idx], sample_weight=fit_weights)
        return platt.predict_proba(scores[eval_idx, None])[:, 1]
    isotonic = IsotonicRegression(out_of_bounds="clip")
    isotonic.fit(scores[fit_idx], labels[fit_idx], sample_weight=fit_weights)
    return isotonic.predict(scores[eval_idx])


def _slice_metrics(scored: pd.DataFrame) -> dict:
    """Each stego slice is scored against all clean test rows, so every slice is a balanced-ish binary task."""
    clean, stego = scored[scored["label"] == 0], scored[scored["label"] == 1]
    slices: dict[str, dict] = {}
    for column in SLICE_COLUMNS:
        for value, group in stego.groupby(column):
            slices[f"{column}={value}"] = _binary_metrics(pd.concat([clean, group]))
    for values, group in stego.groupby(list(SLICE_COLUMNS)):
        name = "|".join(f"{column}={value}" for column, value in zip(SLICE_COLUMNS, values, strict=True))
        slices[name] = _binary_metrics(pd.concat([clean, group]))
    return slices


def _binary_metrics(scored: pd.DataFrame) -> dict:
    labels, probabilities = scored["label"].to_numpy(), scored["probability"].to_numpy()
    predicted = (probabilities >= DECISION_THRESHOLD).astype(int)
    weights = balanced_sample_weights(scored["label"])
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "accuracy": float(accuracy_score(labels, predicted)),
        "balanced_accuracy": float(accuracy_score(labels, predicted, sample_weight=weights)),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "brier": float(brier_score_loss(labels, probabilities, sample_weight=weights)),
        "n_clean": int((labels == 0).sum()),
        "n_stego": int((labels == 1).sum()),
    }


def _write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the calibrated Random Forest steganalysis detector.")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_CSV)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


if __name__ == "__main__":
    main()
