"""Visual quality: PSNR and SSIM between each held-out cover and its stego image.

Payload ratios 5/10/25/50 % x LSB replacement / matching, pseudorandom layout
(the real pipeline's layout). Payloads are seeded random bytes, which embed
exactly like an encrypted message (see ml/dataset.py) and keep reruns identical.

Usage:
    python -m experiments.quality
    python -m experiments.quality --seed 2026 --covers 20
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from experiments.common import (
    SERIES_STYLES,
    assert_held_out,
    base_argument_parser,
    held_out_cover_ids,
    load_cover,
    save_figure,
    seeded_key,
    write_results,
)
from ml.dataset import ALGORITHMS, PAYLOAD_RATIOS, StegoVariant, make_stego_image

PIXEL_RANGE = 255


@dataclass(frozen=True)
class QualityScore:
    """How close a stego image is to its cover."""

    psnr_db: float
    ssim: float


def main() -> None:
    """Command-line entry point."""
    args = base_argument_parser("PSNR and SSIM per payload ratio on held-out covers.").parse_args()
    cover_ids = held_out_cover_ids(limit=args.covers)
    assert_held_out(cover_ids)
    print(f"[*] quality: {len(cover_ids)} held-out covers, seed={args.seed}")
    scores = run_quality(cover_ids, seed=args.seed, cover_dir=args.cover_dir, workers=args.workers)
    summary = summarise_quality(scores)
    print(summary.to_string(index=False))
    print(f"[+] {write_results(scores, 'quality')}, {write_results(summary, 'quality_summary')}")
    print(f"[+] {save_figure(plot_quality(summary), 'quality')}")


def measure_quality(cover: Image.Image, stego: Image.Image) -> QualityScore:
    """PSNR (dB) and SSIM (colour, 0-1) of a stego image against its cover."""
    cover_pixels, stego_pixels = np.asarray(cover.convert("RGB")), np.asarray(stego.convert("RGB"))
    return QualityScore(
        psnr_db=float(peak_signal_noise_ratio(cover_pixels, stego_pixels, data_range=PIXEL_RANGE)),
        ssim=float(structural_similarity(cover_pixels, stego_pixels, data_range=PIXEL_RANGE, channel_axis=-1)),
    )


def quality_at_ratio(cover: Image.Image, ratio: float, algorithm: str, key: bytes) -> QualityScore:
    """Embed seeded random bytes filling `ratio` of the cover, then measure quality."""
    stego = make_stego_image(cover, StegoVariant(ratio, "pseudorandom", algorithm), key)
    return measure_quality(cover, stego)


def run_quality(cover_ids: list[str], seed: int, cover_dir: Path, workers: int = 1) -> pd.DataFrame:
    """One row per cover x ratio x algorithm."""
    rows_for = partial(_cover_rows, seed=seed, cover_dir=cover_dir)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_cover = list(pool.map(rows_for, cover_ids))
    else:
        per_cover = [rows_for(cover_id) for cover_id in cover_ids]
    return pd.DataFrame([row for rows in per_cover for row in rows])


def summarise_quality(scores: pd.DataFrame) -> pd.DataFrame:
    """Mean and standard deviation of PSNR and SSIM per ratio and algorithm."""
    summary = scores.groupby(["algorithm", "ratio"]).agg(
        psnr_mean=("psnr_db", "mean"),
        psnr_std=("psnr_db", "std"),
        ssim_mean=("ssim", "mean"),
        ssim_std=("ssim", "std"),
        n_covers=("cover_id", "nunique"),
        seed=("seed", "first"),
    )
    return summary.reset_index()


def plot_quality(summary: pd.DataFrame) -> Figure:
    """PSNR and SSIM against payload ratio, one line per algorithm, error bars = 1 std."""
    figure, (psnr_axis, ssim_axis) = plt.subplots(1, 2, figsize=(9, 3.6))
    for style, (algorithm, rows) in zip(SERIES_STYLES, summary.groupby("algorithm"), strict=False):
        percent = rows["ratio"] * 100
        label = f"LSB {algorithm}"
        psnr_axis.errorbar(percent, rows["psnr_mean"], yerr=rows["psnr_std"], label=label, capsize=3, **style)
        ssim_axis.errorbar(percent, rows["ssim_mean"], yerr=rows["ssim_std"], label=label, capsize=3, **style)
    psnr_axis.set(xlabel="Payload (% of LSB slots)", ylabel="PSNR (dB)", title="Peak signal-to-noise ratio")
    ssim_axis.set(xlabel="Payload (% of LSB slots)", ylabel="SSIM (0–1)", title="Structural similarity")
    for axis in (psnr_axis, ssim_axis):
        axis.grid(True, color="0.85")
        axis.legend()
    figure.tight_layout()
    return figure


def _cover_rows(cover_id: str, seed: int, cover_dir: Path) -> list[dict]:
    cover = load_cover(cover_id, cover_dir)
    rows = []
    for ratio, algorithm in product(PAYLOAD_RATIOS, ALGORITHMS):
        score = quality_at_ratio(cover, ratio, algorithm, seeded_key(seed, "quality", cover_id, ratio, algorithm))
        rows.append({"cover_id": cover_id, "ratio": ratio, "algorithm": algorithm, **asdict(score), "seed": seed})
    return rows


if __name__ == "__main__":
    main()
