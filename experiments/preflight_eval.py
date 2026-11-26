"""Pre-flight validity: does a predicted risk level match the actual detection rate?

For each held-out cover, algorithm and standard payload share (5/10/25/50 %):

- predicted: the pre-flight check's simulated risk (seeded random bytes)
- actual:    a real format-v2 message of the same size is hidden with the real
             pipeline, and the detector decides stego / clean at its threshold

Covers are split into smooth and textured at the median texture complexity
(Laplacian variance), to test whether the prediction holds for both kinds.
Message content and the prediction are seeded; the pipeline's keys come from
os.urandom as in production, so actual probabilities vary slightly between runs.

Usage:
    python -m experiments.preflight_eval
    python -m experiments.preflight_eval --covers 30 --workers 7
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from PIL import Image

from core.keys import generate_keypair
from core.pipeline import stego_encode_asymmetric
from experiments.common import (
    BAR_HATCHES,
    assert_held_out,
    base_argument_parser,
    held_out_cover_ids,
    load_cover,
    save_figure,
    seeded_bytes,
    seeded_key,
    write_results,
)
from ml.dataset import ALGORITHMS
from ml.detector import DEFAULT_DETECTOR_PATH, StegoDetector
from ml.risk import PreflightChecker, RiskLevel

KEY_MODE = "asymmetric"  # no PBKDF2 per trial; the embedded bits look the same in both modes
SMOOTH, TEXTURED = "smooth", "textured"

_worker_detector: StegoDetector | None = None


def main() -> None:
    """Command-line entry point."""
    parser = base_argument_parser("Predicted pre-flight risk vs actual detection on held-out covers.")
    parser.add_argument("--model", type=Path, default=DEFAULT_DETECTOR_PATH)
    args = parser.parse_args()
    cover_ids = held_out_cover_ids(limit=args.covers)
    assert_held_out(cover_ids)
    print(f"[*] preflight_eval: {len(cover_ids)} held-out covers x {len(ALGORITHMS)} algorithms, seed={args.seed}")
    trials = label_texture(run_preflight_eval(cover_ids, args.seed, args.cover_dir, args.model, args.workers))
    summary = summarise_by_level(trials)
    print(summary.to_string(index=False))
    print(f"[+] {write_results(trials, 'preflight_eval')}, {write_results(summary, 'preflight_eval_summary')}")
    print(f"[+] {save_figure(plot_detection_by_level(summary), 'preflight_validity')}")


def evaluate_cover(cover: Image.Image, detector: StegoDetector, seed: int, cover_id: str) -> list[dict]:
    """Predicted vs actual detection for every algorithm x standard payload share on one cover."""
    _, public_key = generate_keypair()
    rows = []
    for algorithm in ALGORITHMS:
        prediction = PreflightChecker(detector, seed=seed).check(cover, 0, key_mode=KEY_MODE, algorithm=algorithm)
        for predicted in prediction.ratio_risks:
            if predicted.message_bytes < 1:
                continue  # share smaller than the format overhead (tiny covers only): nothing to hide
            message = seeded_bytes(
                seeded_key(seed, "preflight", cover_id, algorithm, predicted.ratio), predicted.message_bytes
            )
            stego = stego_encode_asymmetric(cover, message, public_key, algorithm=algorithm)
            actual_probability = detector.predict_probability(stego)
            rows.append(
                {
                    "cover_id": cover_id,
                    "algorithm": algorithm,
                    "ratio": predicted.ratio,
                    "message_bytes": predicted.message_bytes,
                    "predicted_probability": predicted.probability,
                    "predicted_level": predicted.level.value,
                    "actual_probability": actual_probability,
                    "detected": actual_probability >= detector.threshold,
                    "texture_complexity": prediction.texture_complexity,
                    "seed": seed,
                }
            )
    return rows


def run_preflight_eval(
    cover_ids: list[str], seed: int, cover_dir: Path, model_path: Path, workers: int = 1
) -> pd.DataFrame:
    """One row per cover x algorithm x payload share."""
    rows_for = partial(_cover_rows, seed=seed, cover_dir=cover_dir)
    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_load_worker_detector, initargs=(model_path,)
        ) as pool:
            per_cover = list(pool.map(rows_for, cover_ids))
    else:
        _load_worker_detector(model_path)
        per_cover = [rows_for(cover_id) for cover_id in cover_ids]
    return pd.DataFrame([row for rows in per_cover for row in rows])


def label_texture(trials: pd.DataFrame) -> pd.DataFrame:
    """Add a smooth / textured label, split at the median texture complexity of the covers."""
    per_cover = trials.groupby("cover_id")["texture_complexity"].first()
    median = per_cover.median()
    return trials.assign(texture=np.where(trials["texture_complexity"] < median, SMOOTH, TEXTURED))


def summarise_by_level(trials: pd.DataFrame) -> pd.DataFrame:
    """Actual detection rate per predicted level, for all covers and per texture group."""
    groups = [trials.assign(texture="all"), trials]
    pooled = pd.concat(groups, ignore_index=True)
    summary = pooled.groupby(["texture", "predicted_level"]).agg(
        n_trials=("detected", "size"),
        actual_detection_rate=("detected", "mean"),
        mean_predicted_probability=("predicted_probability", "mean"),
        mean_actual_probability=("actual_probability", "mean"),
    )
    levels = [level.value for level in RiskLevel]
    summary = summary.reset_index()
    summary["predicted_level"] = pd.Categorical(summary["predicted_level"], categories=levels, ordered=True)
    return summary.sort_values(["texture", "predicted_level"]).assign(seed=trials["seed"].iloc[0])


def plot_detection_by_level(summary: pd.DataFrame) -> Figure:
    """Grouped bars: actual detection rate per predicted level, smooth vs textured covers."""
    figure, axis = plt.subplots(figsize=(6.5, 3.8))
    levels = [level.value for level in RiskLevel]
    positions = np.arange(len(levels))
    width = 0.38
    for offset, (texture, shade, hatch) in zip(
        (-width / 2, width / 2), ((SMOOTH, "0.85", BAR_HATCHES[1]), (TEXTURED, "0.35", BAR_HATCHES[0])), strict=True
    ):
        rows = summary[summary["texture"] == texture].set_index("predicted_level").reindex(levels)
        rates = rows["actual_detection_rate"].fillna(0).to_numpy() * 100
        bars = axis.bar(
            positions + offset,
            rates,
            width,
            color=shade,
            edgecolor="black",
            hatch=hatch,
            label=f"{texture.title()} covers",
        )
        counts = rows["n_trials"].fillna(0).astype(int)
        axis.bar_label(bars, labels=[f"n={n}" for n in counts], fontsize=8, padding=2)
    axis.set_xticks(positions, [f"Predicted {level}" for level in levels])
    axis.set(ylabel="Actually detected (%)", ylim=(0, 110), title="Pre-flight prediction vs actual detection")
    axis.legend(loc="upper left")
    figure.tight_layout()
    return figure


def _load_worker_detector(model_path: Path) -> None:
    global _worker_detector  # one model load per worker process, not per cover
    _worker_detector = StegoDetector(model_path)


def _cover_rows(cover_id: str, seed: int, cover_dir: Path) -> list[dict]:
    assert _worker_detector is not None, "detector is loaded by the pool initializer"
    return evaluate_cover(load_cover(cover_id, cover_dir), _worker_detector, seed, cover_id)


if __name__ == "__main__":
    main()
