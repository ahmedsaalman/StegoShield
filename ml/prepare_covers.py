"""Cut DIV2K photographs into 512x512 PNG cover images.

Each source photo yields CROPS_PER_SOURCE crops, picked with a fixed seed from an
evenly spaced grid of candidate positions. Crops are cut, never resized:
resampling would smooth away the natural pixel noise that real covers have.

Cover files are named ``<source_id>_<k>.png`` (e.g. ``0801_2.png``). The source
id is kept so that train/test splits can group all crops of one photo together.

Two DIV2K sets are used, with disjoint photo ids, so source ids stay unique:
- valid: 100 photos (0801-0900), 5 crops each = 500 covers   (~430 MB download)
- train: 800 photos (0001-0800), 2 crops each = 1,600 covers (~3.5 GB download)
More source photos matter more than more crops of the same photo: the detector is
split and evaluated by source photo.

Usage:
    python -m ml.prepare_covers                     # both sets; downloads whatever is missing
    python -m ml.prepare_covers --sets valid        # only the original 500 covers
"""

from __future__ import annotations

import argparse
import math
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

DIV2K_BASE_URL = "https://data.vision.ee.ethz.ch/cvl/DIV2K"
DEFAULT_RAW_DIR = Path("data/raw/div2k")
DEFAULT_COVER_DIR = Path("data/covers")
COVER_SIZE_PX = 512
CROPS_PER_SOURCE = 5
DEFAULT_SEED = 2026


@dataclass(frozen=True)
class SourceSet:
    """One DIV2K download: where it lives, how many crops to cut per photo, and its seed offset."""

    archive: str
    folder: str
    crops_per_source: int
    seed_offset: int
    size_note: str


SOURCE_SETS = {
    "valid": SourceSet("DIV2K_valid_HR.zip", "DIV2K_valid_HR", CROPS_PER_SOURCE, 0, "~430 MB"),
    "train": SourceSet("DIV2K_train_HR.zip", "DIV2K_train_HR", 2, 1, "~3.5 GB"),
}
DEFAULT_SETS = ("valid", "train")


def main() -> None:
    """Command-line entry point."""
    args = _parse_args()
    total = 0
    for name in args.sets:
        source_set = SOURCE_SETS[name]
        source_dir = args.raw / source_set.folder
        if not source_dir.is_dir():
            download_div2k(args.raw, source_set)
        seed = args.seed + source_set.seed_offset
        written = prepare_covers(source_dir, args.out, source_set.crops_per_source, args.size, seed)
        print(f"[+] {name}: wrote {len(written)} covers to {args.out} (seed={seed})")
        total += len(written)
    print(f"[+] {total} covers in total")


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


def download_div2k(raw_dir: Path, source_set: SourceSet) -> None:
    """Download (if needed) and unzip one DIV2K set into raw_dir."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / source_set.archive
    if not zip_path.exists():
        url = f"{DIV2K_BASE_URL}/{source_set.archive}"
        print(f"[*] Downloading {url} ({source_set.size_note})...")
        urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(raw_dir)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cut DIV2K photos into 512x512 PNG covers.")
    parser.add_argument("--sets", nargs="+", choices=sorted(SOURCE_SETS), default=list(DEFAULT_SETS))
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_DIR, help="Folder holding the DIV2K downloads")
    parser.add_argument("--out", type=Path, default=DEFAULT_COVER_DIR, help="Output folder for covers")
    parser.add_argument("--size", type=int, default=COVER_SIZE_PX, help="Crop side length in pixels")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


if __name__ == "__main__":
    main()
