"""Build the labelled feature table used to train and evaluate the detector.

For every cover image this writes one clean row (label 0) and one stego row
(label 1) per variant: payload ratio x layout x algorithm, 16 variants by default.

Why stego images use seeded random bytes instead of real v2 messages: format v2
draws its salt, nonce and keys from os.urandom, which would make the table
non-reproducible. Its embedded bits are indistinguishable from random bytes
(see tests/test_security.py), and the slot selection and LSB replacement /
+/-1 code are the same, so the pixel statistics the detector sees are the same.

Usage:
    python -m ml.dataset                          # data/covers -> data/features/features.csv
    python -m ml.dataset --seed 2026 --workers 7
"""

from __future__ import annotations

import argparse
import hashlib
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import partial
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from core.embed import EmbeddingAlgorithm, EmbeddingMode, embed_payload
from ml.features import FEATURE_NAMES, extract_features

PAYLOAD_RATIOS = (0.05, 0.10, 0.25, 0.50)
LAYOUTS: tuple[EmbeddingMode, ...] = ("sequential", "pseudorandom")
ALGORITHMS: tuple[EmbeddingAlgorithm, ...] = ("replacement", "matching")
LENGTH_PREFIX_BYTES = 4  # embed_payload stores a 32-bit length before the payload

DEFAULT_COVER_DIR = Path("data/covers")
DEFAULT_OUTPUT_CSV = Path("data/features/features.csv")
DEFAULT_SEED = 2026
CSV_FLOAT_FORMAT = "%.12g"

META_COLUMNS = ["cover_id", "source_id", "label", "ratio", "layout", "algorithm", "seed"]
CLEAN_LABEL, STEGO_LABEL = 0, 1


@dataclass(frozen=True)
class StegoVariant:
    """One way of embedding: how much, where, and how."""

    ratio: float
    layout: EmbeddingMode
    algorithm: EmbeddingAlgorithm


DEFAULT_VARIANTS = tuple(StegoVariant(r, lay, alg) for r, lay, alg in product(PAYLOAD_RATIOS, LAYOUTS, ALGORITHMS))


def main() -> None:
    """Command-line entry point."""
    args = _parse_args()
    cover_paths = sorted(args.covers.glob("*.png"))
    if not cover_paths:
        raise SystemExit(f"No PNG covers in {args.covers}. Run `python -m ml.prepare_covers` first.")
    print(f"[*] {len(cover_paths)} covers x {len(DEFAULT_VARIANTS)} variants, {args.workers} workers, seed={args.seed}")
    table = build_feature_table(cover_paths, seed=args.seed, workers=args.workers)
    write_feature_table(table, args.out)
    print(f"[+] Wrote {len(table)} rows x {len(FEATURE_NAMES)} features to {args.out}")


def build_feature_table(
    cover_paths: list[Path],
    seed: int = DEFAULT_SEED,
    variants: tuple[StegoVariant, ...] = DEFAULT_VARIANTS,
    workers: int = 1,
) -> pd.DataFrame:
    """Clean + stego feature rows for every cover, in a deterministic order."""
    make_rows = partial(cover_rows, seed=seed, variants=variants)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_cover = list(pool.map(make_rows, cover_paths, chunksize=4))
    else:
        per_cover = [make_rows(path) for path in cover_paths]
    rows = [row for cover in per_cover for row in cover]
    return pd.DataFrame(rows, columns=META_COLUMNS + FEATURE_NAMES)


def write_feature_table(table: pd.DataFrame, out_path: Path) -> None:
    """Write the table as CSV with fixed float formatting, so reruns are byte-identical."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False, float_format=CSV_FLOAT_FORMAT)


def cover_rows(cover_path: Path, seed: int, variants: tuple[StegoVariant, ...]) -> list[dict]:
    """One clean row and one row per stego variant for a single cover."""
    with Image.open(cover_path) as opened:
        cover = opened.convert("RGB")
    cover_id = cover_path.stem
    base = {"cover_id": cover_id, "source_id": source_id_of(cover_path), "seed": seed}

    rows = [_feature_row(cover, base | {"label": CLEAN_LABEL, "ratio": 0.0, "layout": "none", "algorithm": "none"})]
    for variant in variants:
        stego = make_stego_image(cover, variant, sample_key(seed, cover_id, variant))
        meta = {"label": STEGO_LABEL, "ratio": variant.ratio, "layout": variant.layout, "algorithm": variant.algorithm}
        rows.append(_feature_row(stego, base | meta))
    return rows


def make_stego_image(cover: Image.Image, variant: StegoVariant, key: bytes) -> Image.Image:
    """Embed seeded random bytes filling `variant.ratio` of the cover's LSB slots."""
    total_slots = cover.width * cover.height * 3
    payload = np.random.default_rng(int.from_bytes(key, "big")).bytes(
        payload_bytes_for_ratio(total_slots, variant.ratio)
    )
    perm_key = key if variant.layout == "pseudorandom" else None
    return embed_payload(cover, payload, perm_key=perm_key, mode=variant.layout, algorithm=variant.algorithm)


def payload_bytes_for_ratio(total_slots: int, ratio: float) -> int:
    """Payload size (bytes) so that payload + length prefix fills `ratio` of the slots."""
    return max(1, int(total_slots * ratio) // 8 - LENGTH_PREFIX_BYTES)


def sample_key(seed: int, cover_id: str, variant: StegoVariant) -> bytes:
    """Deterministic 32-byte key per (seed, cover, variant): seeds both payload and slot positions."""
    label = f"{seed}|{cover_id}|{variant.ratio}|{variant.layout}|{variant.algorithm}"
    return hashlib.sha256(label.encode("utf-8")).digest()


def source_id_of(cover_path: Path) -> str:
    """Source photo id from a cover name like '0801_2.png' (all crops of one photo share it)."""
    return cover_path.stem.split("_")[0]


def generate_synthetic_covers(output_dir: Path, count: int = 4, size: tuple[int, int] = (64, 64)) -> list[Path]:
    """Small synthetic covers (gradient, noise, blocks, waves) for unit tests only."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(DEFAULT_SEED)
    width, height = size
    xx, yy = np.meshgrid(np.linspace(30, 220, width), np.linspace(40, 200, height))
    patterns = [
        np.stack([xx, yy, (xx + yy) / 2], axis=-1),
        rng.integers(20, 240, size=(height, width, 3)),
        np.repeat(np.kron(rng.integers(0, 256, size=(4, 4)), np.ones((height // 4, width // 4)))[..., None], 3, -1),
        np.stack([np.sin(xx / 9) * 100 + 128, np.cos(yy / 9) * 100 + 128, (xx + yy) / 2], axis=-1),
    ]
    paths = []
    for i in range(count):
        path = output_dir / f"synth{i:02d}_0.png"
        Image.fromarray(np.clip(patterns[i % len(patterns)], 0, 255).astype(np.uint8)).save(path)
        paths.append(path)
    return paths


def _feature_row(image: Image.Image, meta: dict) -> dict:
    _, features = extract_features(image)
    return meta | features


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the clean/stego feature table.")
    parser.add_argument("--covers", type=Path, default=DEFAULT_COVER_DIR, help="Folder of PNG covers")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_CSV, help="Output CSV path")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    return parser.parse_args()


if __name__ == "__main__":
    main()
