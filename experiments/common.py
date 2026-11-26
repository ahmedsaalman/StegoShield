"""Shared helpers for the experiment scripts: held-out covers, seeds, output files, plot style.

Every experiment runs on covers from the detector's **test** split only. The split
is recreated from the feature table with the seed stored in the model artifact,
saved to `experiments/results/split.csv`, and every script checks its covers
against that file before running.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # scripts write files; never open a window

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from PIL import Image

from ml.dataset import DEFAULT_COVER_DIR, DEFAULT_SEED
from ml.detector import DEFAULT_DETECTOR_PATH, load_detector_artifact
from ml.train_detector import DEFAULT_FEATURES_CSV, load_feature_table, split_by_source

RESULTS_DIR = Path("experiments/results")
FIGURES_DIR = Path("docs/figures")
SPLIT_FILE = RESULTS_DIR / "split.csv"
CSV_FLOAT_FORMAT = "%.6g"
FIGURE_DPI = 150

# Black and greys with distinct line styles and markers, so figures survive greyscale printing.
SERIES_STYLES = (
    {"color": "black", "linestyle": "-", "marker": "o"},
    {"color": "0.45", "linestyle": "--", "marker": "s"},
    {"color": "0.25", "linestyle": ":", "marker": "^"},
    {"color": "0.6", "linestyle": "-.", "marker": "D"},
)
BAR_HATCHES = ("", "///", "...", "xx")


class LeakageError(RuntimeError):
    """A cover used for evaluation was part of the detector's training data."""


def write_split_file(
    features_csv: Path = DEFAULT_FEATURES_CSV,
    model_path: Path = DEFAULT_DETECTOR_PATH,
    out_path: Path = SPLIT_FILE,
) -> pd.DataFrame:
    """Recreate the detector's train/test split from its stored seed and save one row per cover.

    Raises:
        DetectorNotTrainedError: If there is no trained model.
        LeakageError: If any cover or source photo ends up on both sides.
    """
    seed = load_detector_artifact(model_path)["seed"]
    split = split_by_source(load_feature_table(features_csv), seed=seed)
    frame = pd.concat([_cover_sides(split.train, "train"), _cover_sides(split.test, "test")], ignore_index=True)
    check_split_is_disjoint(frame)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.assign(seed=seed).to_csv(out_path, index=False)
    return frame


def check_split_is_disjoint(split: pd.DataFrame) -> None:
    """Raise if a cover or a source photo appears on both the train and test side.

    Raises:
        LeakageError: If the sides overlap.
    """
    for column in ("cover_id", "source_id"):
        sides_per_id = split.groupby(column)["side"].nunique()
        overlapping = sides_per_id[sides_per_id > 1].index.tolist()
        if overlapping:
            raise LeakageError(f"{len(overlapping)} {column} values are on both sides, e.g. {overlapping[:3]}")


def load_split(split_file: Path = SPLIT_FILE) -> pd.DataFrame:
    """The saved train/test split, rebuilt from the detector's seed if the file is missing."""
    return pd.read_csv(split_file, dtype=str) if split_file.exists() else write_split_file(out_path=split_file)


def held_out_cover_ids(split_file: Path = SPLIT_FILE, limit: int | None = None) -> list[str]:
    """Test-side cover ids in a fixed order; builds the split file first if it is missing."""
    split = load_split(split_file)
    cover_ids = sorted(split.loc[split["side"] == "test", "cover_id"].astype(str))
    return cover_ids[:limit] if limit else cover_ids


def assert_held_out(cover_ids: Iterable[str], split_file: Path = SPLIT_FILE) -> None:
    """Raise unless every cover id is on the test side of the saved split.

    Raises:
        LeakageError: If a cover was used in training or is not in the split at all.
    """
    split = load_split(split_file)
    test_ids = set(split.loc[split["side"] == "test", "cover_id"])
    not_held_out = sorted(set(cover_ids) - test_ids)
    if not_held_out:
        raise LeakageError(f"{len(not_held_out)} covers are not held out, e.g. {not_held_out[:3]}")


def load_cover(cover_id: str, cover_dir: Path = DEFAULT_COVER_DIR) -> Image.Image:
    """Open a cover PNG as RGB."""
    with Image.open(cover_dir / f"{cover_id}.png") as opened:
        return opened.convert("RGB")


def seeded_key(seed: int, *parts: object) -> bytes:
    """Deterministic 32-byte key for one (seed, cover, condition) combination."""
    label = "|".join(str(part) for part in (seed, *parts))
    return hashlib.sha256(label.encode("utf-8")).digest()


def seeded_bytes(key: bytes, length: int) -> bytes:
    """`length` reproducible random bytes derived from `key`."""
    return np.random.default_rng(int.from_bytes(key, "big")).bytes(length)


def write_results(frame: pd.DataFrame, name: str, results_dir: Path = RESULTS_DIR) -> Path:
    """Save a results table as `<results_dir>/<name>.csv` with fixed float formatting."""
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{name}.csv"
    frame.to_csv(path, index=False, float_format=CSV_FLOAT_FORMAT)
    return path


def save_figure(figure: Figure, name: str, figures_dir: Path = FIGURES_DIR) -> Path:
    """Save a figure as `<figures_dir>/<name>.png`."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / f"{name}.png"
    figure.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    return path


def base_argument_parser(description: str) -> argparse.ArgumentParser:
    """Arguments every experiment script shares."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed for payloads and messages")
    parser.add_argument("--covers", type=int, default=None, help="Use only the first N held-out covers")
    parser.add_argument("--cover-dir", type=Path, default=DEFAULT_COVER_DIR)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    return parser


def _cover_sides(frame: pd.DataFrame, side: str) -> pd.DataFrame:
    return frame[["cover_id", "source_id"]].drop_duplicates().assign(side=side)
