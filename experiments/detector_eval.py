"""Detector performance on held-out covers: ROC curves and metrics per condition.

Scores the test rows of the feature table with the committed model, then
reports accuracy, precision, recall and ROC-AUC per payload ratio x layout x
algorithm (each slice = all clean test covers + that slice's stego images).

Usage:
    python -m experiments.detector_eval
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure
from PIL import Image
from sklearn.metrics import roc_curve

from experiments.common import (
    SERIES_STYLES,
    LeakageError,
    assert_held_out,
    base_argument_parser,
    save_figure,
    seeded_key,
    write_results,
)
from ml.dataset import ALGORITHMS, PAYLOAD_RATIOS, StegoVariant, make_stego_image
from ml.detector import DEFAULT_DETECTOR_PATH, StegoDetector, load_detector_artifact
from ml.features import FEATURE_NAMES
from ml.train_detector import DEFAULT_FEATURES_CSV, evaluate_detector, load_feature_table, split_by_source

SLICE_KEYS = ("ratio", "layout", "algorithm")
ROC_LAYOUT = "pseudorandom"  # the real pipeline's layout; sequential is reported in the table only


def main() -> None:
    """Command-line entry point."""
    parser = base_argument_parser("ROC curves and per-condition metrics on held-out covers.")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_CSV)
    parser.add_argument("--model", type=Path, default=DEFAULT_DETECTOR_PATH)
    args = parser.parse_args()

    artifact = load_detector_artifact(args.model)
    test = held_out_rows(load_feature_table(args.features), seed=artifact["seed"])
    assert_held_out(test["cover_id"].unique())
    print(f"[*] detector_eval: {test['cover_id'].nunique()} held-out covers, {len(test)} rows, seed={artifact['seed']}")

    scored = score_rows(artifact, test)
    table = slice_metrics_table(artifact, test)
    print(table.to_string(index=False))
    print(f"[+] {write_results(table, 'detector_metrics')}")
    print(f"[+] {save_figure(plot_roc_curves(scored), 'detector_roc')}")


def held_out_rows(table: pd.DataFrame, seed: int) -> pd.DataFrame:
    """The detector's test split, recreated with the seed it was trained with.

    Raises:
        LeakageError: If the recreated split shares a source photo with training.
    """
    split = split_by_source(table, seed=seed)
    shared = set(split.train["source_id"]) & set(split.test["source_id"])
    if shared:
        raise LeakageError(f"{len(shared)} source photos are on both sides of the split")
    return split.test


def score_rows(artifact: dict, rows: pd.DataFrame) -> pd.DataFrame:
    """Add the detector's probability to each feature row."""
    probabilities = artifact["model"].predict_proba(rows[FEATURE_NAMES].to_numpy())[:, 1]
    return rows.assign(probability=probabilities)


def slice_metrics_table(artifact: dict, test: pd.DataFrame) -> pd.DataFrame:
    """One row per ratio x layout x algorithm, plus an overall row, with the seed recorded."""
    metrics = evaluate_detector(artifact, test)
    rows = [{"ratio": "all", "layout": "all", "algorithm": "all", **metrics["overall"]}]
    for name, values in metrics["per_slice"].items():
        keys = dict(part.split("=") for part in name.split("|"))
        if set(keys) == set(SLICE_KEYS):
            rows.append({**keys, **values})
    return pd.DataFrame(rows).assign(seed=artifact["seed"])


def roc_for_slice(scored: pd.DataFrame, ratio: float, algorithm: str, layout: str = ROC_LAYOUT) -> tuple:
    """False/true positive rates for clean covers vs one stego condition."""
    is_slice = (scored["ratio"] == ratio) & (scored["algorithm"] == algorithm) & (scored["layout"] == layout)
    rows = scored[(scored["label"] == 0) | is_slice]
    false_positive_rate, true_positive_rate, _ = roc_curve(rows["label"], rows["probability"])
    return false_positive_rate, true_positive_rate


def score_payload_variants(cover: Image.Image, detector: StegoDetector, seed: int, label: str) -> list[dict]:
    """Detector probability for one cover with seeded random payloads at every ratio x algorithm."""
    rows = []
    for algorithm, ratio in product(ALGORITHMS, PAYLOAD_RATIOS):
        key = seeded_key(seed, "detector-compare", label, ratio, algorithm)
        stego = make_stego_image(cover, StegoVariant(ratio, ROC_LAYOUT, algorithm), key)
        rows.append({"algorithm": algorithm, "ratio": ratio, "probability": detector.predict_probability(stego)})
    return rows


def plot_roc_curves(scored: pd.DataFrame) -> Figure:
    """One panel per algorithm, one ROC curve per payload ratio (pseudorandom layout)."""
    figure, axes = plt.subplots(1, len(ALGORITHMS), figsize=(9, 4), sharey=True)
    for axis, algorithm in zip(axes, ALGORITHMS, strict=True):
        for style, ratio in zip(SERIES_STYLES, PAYLOAD_RATIOS, strict=True):
            false_positive_rate, true_positive_rate = roc_for_slice(scored, ratio, algorithm)
            axis.plot(false_positive_rate, true_positive_rate, label=f"{ratio:.0%} payload", markevery=0.1, **style)
        axis.plot([0, 1], [0, 1], color="0.7", linewidth=0.8, label="Chance")
        axis.set(
            xlabel="False positive rate (clean flagged)",
            title=f"LSB {algorithm}, {ROC_LAYOUT} layout",
            xlim=(0, 1),
            ylim=(0, 1.01),
        )
        axis.grid(True, color="0.9")
        axis.legend(loc="lower right")
    axes[0].set_ylabel("True positive rate (stego detected)")
    figure.tight_layout()
    return figure


if __name__ == "__main__":
    main()
