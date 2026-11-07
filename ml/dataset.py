"""StegoShield Stego-Cover Dataset Generator (Task L17).

Generates paired clean and stego image datasets for ML steganalysis training:
- Parameterized payload ratios: 5%, 10%, 25%, 50% of carrier capacity.
- Embedding modes: Pseudorandom and Sequential.
- Embedding algorithms: LSB Replacement and LSB Matching (+/-1).
- Extracts all 27 statistical features into tabular format (CSV / DataFrame).
- Prevents data leakage by partitioning train/val/test splits strictly by cover image ID.
- Includes synthetic cover generation for local rapid experimentation and testing.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
import numpy as np
import pandas as pd

from core.capacity import calculate_image_capacity
from core.embed import embed_payload, EmbeddingMode, EmbeddingAlgorithm
from ml.features import extract_features, FEATURE_NAMES


DEFAULT_PAYLOAD_RATIOS = [0.05, 0.10, 0.25, 0.50]


def generate_synthetic_covers(output_dir: Path | str, count: int = 10, size: Tuple[int, int] = (128, 128)) -> list[Path]:
    """Generate synthetic cover images with diverse textures for local testing."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    rng = np.random.default_rng(2026)

    for i in range(count):
        img_type = i % 4
        w, h = size
        if img_type == 0:
            # Smooth gradient (high detectability risk)
            x = np.linspace(30, 220, w, dtype=np.uint8)
            y = np.linspace(40, 200, h, dtype=np.uint8)
            xx, yy = np.meshgrid(x, y)
            arr = np.stack([xx, yy, ((xx.astype(int) + yy.astype(int)) // 2).astype(np.uint8)], axis=-1)
        elif img_type == 1:
            # High-texture noise / grass-like (low detectability risk)
            arr = rng.integers(20, 240, size=(h, w, 3), dtype=np.uint8)
        elif img_type == 2:
            # Geometric blocks & edges
            arr = np.zeros((h, w, 3), dtype=np.uint8)
            for _ in range(6):
                x1, y1 = rng.integers(0, w - 20), rng.integers(0, h - 20)
                bw, bh = rng.integers(15, 40), rng.integers(15, 40)
                color = rng.integers(0, 256, size=3, dtype=np.uint8)
                arr[y1 : y1 + bh, x1 : x1 + bw] = color
        else:
            # Sinusoidal / wave pattern
            x = np.sin(np.linspace(0, 10, w)) * 100 + 128
            y = np.cos(np.linspace(0, 10, h)) * 100 + 128
            xx, yy = np.meshgrid(x, y)
            r = np.clip(xx, 0, 255).astype(np.uint8)
            g = np.clip(yy, 0, 255).astype(np.uint8)
            b = np.clip((xx + yy) / 2, 0, 255).astype(np.uint8)
            arr = np.stack([r, g, b], axis=-1)

        img = Image.fromarray(arr, mode="RGB")
        file_path = out_path / f"cover_{i:04d}.png"
        img.save(file_path, format="PNG")
        created.append(file_path)

    return created


def generate_stego_samples_for_cover(
    cover_path: Path | str,
    payload_ratios: list[float] | None = None,
    modes: list[EmbeddingMode] | None = None,
    algorithms: list[EmbeddingAlgorithm] | None = None,
    perm_key: bytes | None = None,
) -> list[dict[str, Any]]:
    """Generate clean and stego records with extracted features for a single cover image.
    
    Returns a list of dictionaries ready to be converted into a DataFrame row.
    """
    if payload_ratios is None:
        payload_ratios = DEFAULT_PAYLOAD_RATIOS
    if modes is None:
        modes = ["pseudorandom", "sequential"]
    if algorithms is None:
        algorithms = ["replacement"]
    if perm_key is None:
        perm_key = b"StegoShieldDatasetSeedKey_2026_!"

    cover_file = Path(cover_path)
    cover_img = Image.open(cover_file).convert("RGB")
    cover_id = cover_file.stem
    cap = calculate_image_capacity(cover_img)
    max_bytes = cap["max_payload_bytes"]

    records: list[dict[str, Any]] = []

    # 1. Clean Cover Record (Class 0)
    clean_vec, clean_feats = extract_features(cover_img)
    clean_record = {
        "cover_id": cover_id,
        "sample_type": "clean",
        "is_stego": 0,
        "payload_ratio": 0.0,
        "payload_bytes": 0,
        "embedding_mode": "none",
        "embedding_algorithm": "none",
        "width": cover_img.width,
        "height": cover_img.height,
    }
    clean_record.update(clean_feats)
    records.append(clean_record)

    # 2. Stego Records (Class 1) across ratios, modes, and algorithms
    rng = np.random.default_rng(int.from_bytes(perm_key[:8], "big"))

    for ratio in payload_ratios:
        num_bytes = max(1, int(max_bytes * ratio))
        random_payload = rng.bytes(num_bytes)

        for mode in modes:
            for algo in algorithms:
                try:
                    stego_img = embed_payload(
                        cover_image=cover_img,
                        payload_bytes=random_payload,
                        perm_key=perm_key if mode == "pseudorandom" else None,
                        mode=mode,
                        algorithm=algo,
                    )
                    _, stego_feats = extract_features(stego_img)

                    rec = {
                        "cover_id": cover_id,
                        "sample_type": "stego",
                        "is_stego": 1,
                        "payload_ratio": ratio,
                        "payload_bytes": num_bytes,
                        "embedding_mode": mode,
                        "embedding_algorithm": algo,
                        "width": cover_img.width,
                        "height": cover_img.height,
                    }
                    rec.update(stego_feats)
                    records.append(rec)
                except Exception as e:
                    # Skip if capacity exceeded
                    continue

    return records


def build_stego_dataset(
    cover_paths: list[Path | str],
    payload_ratios: list[float] | None = None,
    modes: list[EmbeddingMode] | None = None,
    algorithms: list[EmbeddingAlgorithm] | None = None,
) -> pd.DataFrame:
    """Process multiple cover images and aggregate clean & stego features into a DataFrame."""
    all_records: list[dict[str, Any]] = []
    for p in cover_paths:
        recs = generate_stego_samples_for_cover(
            cover_path=p,
            payload_ratios=payload_ratios,
            modes=modes,
            algorithms=algorithms,
        )
        all_records.extend(recs)
    return pd.DataFrame(all_records)


def split_dataset(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split dataset by cover_id to guarantee ZERO data leakage between splits."""
    unique_covers = df["cover_id"].unique()
    rng = np.random.default_rng(random_state)
    shuffled_covers = rng.permutation(unique_covers)

    n_total = len(shuffled_covers)
    n_train = int(n_total * train_ratio)
    n_val = int(n_total * val_ratio)

    train_ids = set(shuffled_covers[:n_train])
    val_ids = set(shuffled_covers[n_train : n_train + n_val])
    test_ids = set(shuffled_covers[n_train + n_val :])

    train_df = df[df["cover_id"].isin(train_ids)].copy()
    val_df = df[df["cover_id"].isin(val_ids)].copy()
    test_df = df[df["cover_id"].isin(test_ids)].copy()

    return train_df, val_df, test_df


def main():
    parser = argparse.ArgumentParser(description="StegoShield Stego-Cover Dataset Generator")
    parser.add_argument("--cover-dir", type=str, default=None, help="Directory of clean cover PNG/JPG images")
    parser.add_argument("--synthetic", type=int, default=0, help="Generate N synthetic covers if no directory provided")
    parser.add_argument("--output-csv", type=str, default="data/stego_features.csv", help="Output CSV path")
    parser.add_argument("--ratios", nargs="+", type=float, default=[0.05, 0.10, 0.25, 0.50])
    args = parser.parse_args()

    cover_paths: list[Path] = []
    if args.cover_dir and Path(args.cover_dir).is_dir():
        cover_paths = list(Path(args.cover_dir).glob("*.png")) + list(Path(args.cover_dir).glob("*.jpg"))
    elif args.synthetic > 0:
        synth_dir = Path("data/synthetic_covers")
        cover_paths = generate_synthetic_covers(synth_dir, count=args.synthetic)
    else:
        print("[-] Please specify --cover-dir or --synthetic N to generate data.")
        return

    print(f"[*] Processing {len(cover_paths)} cover images...")
    df = build_stego_dataset(cover_paths, payload_ratios=args.ratios)
    
    out_file = Path(args.output_csv)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_file, index=False)
    print(f"[+] Successfully extracted {len(df)} samples across {len(FEATURE_NAMES)} features.")
    print(f"    Saved dataset to: {out_file}")


if __name__ == "__main__":
    main()

