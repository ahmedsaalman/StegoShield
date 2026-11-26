"""Cut DIV2K photographs into 512x512 PNG cover images.

Each source photo yields CROPS_PER_SOURCE crops, picked with a fixed seed from an
evenly spaced grid of candidate positions. Crops are cut, never resized:
resampling would smooth away the natural pixel noise that real covers have.

Cover files are named ``<source_id>_<k>.png`` (e.g. ``0801_2.png``). The source
id is kept so that train/test splits can group all crops of one photo together.

Usage:
    python -m ml.prepare_covers                     # uses data/raw/div2k, downloads if missing
    python -m ml.prepare_covers --crops-per-source 5 --seed 2026
"""

from __future__ import annotations

import argparse
import math
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

DIV2K_VALID_URL = "https://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_valid_HR.zip"
DEFAULT_RAW_DIR = Path("data/raw/div2k")
DEFAULT_SOURCE_DIR = DEFAULT_RAW_DIR / "DIV2K_valid_HR"
DEFAULT_COVER_DIR = Path("data/covers")
COVER_SIZE_PX = 512
CROPS_PER_SOURCE = 5
DEFAULT_SEED = 2026


def main() -> None:
    """Command-line entry point."""
    args = _parse_args()
    if not args.source.is_dir():
        download_div2k(args.source.parent)
    written = prepare_covers(args.source, args.out, args.crops_per_source, args.size, args.seed)
    print(f"[+] Wrote {len(written)} covers to {args.out} (seed={args.seed})")


def prepare_covers(
    source_dir: Path,
    cover_dir: Path,
    crops_per_source: int = CROPS_PER_SOURCE,
    size: int = COVER_SIZE_PX,
    seed: int = DEFAULT_SEED,
) -> list[Path]:
    """Cut every PNG in source_dir into crops and save them in cover_dir.

    Raises:
        ValueError: If a source image is smaller than one crop.
    """
    cover_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    written: list[Path] = []
    for source_path in sorted(source_dir.glob("*.png")):
        with Image.open(source_path) as source:
            source_rgb = source.convert("RGB")
        boxes = pick_crop_boxes(source_rgb.size, crops_per_source, size, rng)
        for k, box in enumerate(boxes):
            out_path = cover_dir / f"{source_path.stem}_{k}.png"
            source_rgb.crop(box).save(out_path, format="PNG")
            written.append(out_path)
    return written


def pick_crop_boxes(
    image_size: tuple[int, int],
    count: int,
    size: int,
    rng: np.random.Generator,
) -> list[tuple[int, int, int, int]]:
    """Choose `count` distinct crop boxes from an evenly spaced grid covering the image.

    Raises:
        ValueError: If the image is smaller than one crop or the grid has fewer than `count` boxes.
    """
    candidates = candidate_boxes(image_size, size)
    if len(candidates) < count:
        raise ValueError(f"Image {image_size} only fits {len(candidates)} crops of {size}px, need {count}.")
    chosen = rng.choice(len(candidates), size=count, replace=False)
    return [candidates[i] for i in sorted(chosen)]


def candidate_boxes(image_size: tuple[int, int], size: int) -> list[tuple[int, int, int, int]]:
    """Evenly spaced crop boxes, as many per axis as needed to cover the whole image."""
    width, height = image_size
    if width < size or height < size:
        raise ValueError(f"Image {image_size} is smaller than a {size}px crop.")
    xs = _axis_positions(width, size)
    ys = _axis_positions(height, size)
    return [(x, y, x + size, y + size) for y in ys for x in xs]


def _axis_positions(length: int, size: int) -> list[int]:
    steps = math.ceil(length / size)
    return sorted({round(p) for p in np.linspace(0, length - size, steps)})


def download_div2k(raw_dir: Path) -> None:
    """Download and unzip the DIV2K validation set (100 photos, ~430 MB) into raw_dir."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "DIV2K_valid_HR.zip"
    if not zip_path.exists():
        print(f"[*] Downloading {DIV2K_VALID_URL} (~430 MB)...")
        urllib.request.urlretrieve(DIV2K_VALID_URL, zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(raw_dir)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cut DIV2K photos into 512x512 PNG covers.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_DIR, help="Folder of source PNG photos")
    parser.add_argument("--out", type=Path, default=DEFAULT_COVER_DIR, help="Output folder for covers")
    parser.add_argument("--crops-per-source", type=int, default=CROPS_PER_SOURCE)
    parser.add_argument("--size", type=int, default=COVER_SIZE_PX, help="Crop side length in pixels")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


if __name__ == "__main__":
    main()
