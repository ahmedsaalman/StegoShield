"""Tests for cover preparation (ml/prepare_covers.py) and the feature table (ml/dataset.py)."""

import numpy as np
import pytest
from PIL import Image

from ml.dataset import (
    META_COLUMNS,
    StegoVariant,
    build_feature_table,
    generate_synthetic_covers,
    make_stego_image,
    payload_bytes_for_ratio,
    sample_key,
    source_id_of,
    write_feature_table,
)
from ml.features import FEATURE_NAMES
from ml.prepare_covers import candidate_boxes, pick_crop_boxes, prepare_covers

SMALL_VARIANTS = (
    StegoVariant(0.10, "sequential", "replacement"),
    StegoVariant(0.50, "pseudorandom", "matching"),
)


# ------------------------------------------------------------------ prepare_covers


@pytest.mark.parametrize("size", [(2040, 1356), (2040, 816), (1356, 2040)])
def test_candidate_boxes_cover_div2k_shapes_and_stay_in_bounds(size):
    boxes = candidate_boxes(size, 512)
    assert len(boxes) >= 5
    for left, top, right, bottom in boxes:
        assert 0 <= left and right <= size[0] and 0 <= top and bottom <= size[1]
        assert (right - left, bottom - top) == (512, 512)


def test_pick_crop_boxes_is_deterministic_and_distinct():
    a = pick_crop_boxes((2040, 1356), 5, 512, np.random.default_rng(7))
    b = pick_crop_boxes((2040, 1356), 5, 512, np.random.default_rng(7))
    assert a == b
    assert len(set(a)) == 5


def test_pick_crop_boxes_rejects_too_small_image():
    with pytest.raises(ValueError):
        pick_crop_boxes((400, 400), 1, 512, np.random.default_rng(0))


def test_prepare_covers_writes_named_crops(tmp_path):
    source_dir, cover_dir = tmp_path / "src", tmp_path / "covers"
    source_dir.mkdir()
    rng = np.random.default_rng(1)
    for name in ("0801", "0802"):
        Image.fromarray(rng.integers(0, 256, (300, 450, 3), dtype=np.uint8)).save(source_dir / f"{name}.png")

    written = prepare_covers(source_dir, cover_dir, crops_per_source=3, size=128, seed=3)

    assert sorted(p.name for p in written) == [f"{s}_{k}.png" for s in ("0801", "0802") for k in range(3)]
    assert all(Image.open(p).size == (128, 128) for p in written)


# ------------------------------------------------------------------------ dataset


def test_source_id_groups_crops_of_one_photo(tmp_path):
    assert source_id_of(tmp_path / "0801_3.png") == "0801"


def test_payload_bytes_for_ratio_fills_requested_share():
    total_slots = 512 * 512 * 3
    used_bits = (payload_bytes_for_ratio(total_slots, 0.25) + 4) * 8
    assert abs(used_bits / total_slots - 0.25) < 0.001


def test_make_stego_image_is_deterministic_and_changes_lsbs(tmp_path):
    cover = Image.open(generate_synthetic_covers(tmp_path, count=2)[1])
    variant = SMALL_VARIANTS[1]
    key = sample_key(1, "c", variant)
    first, second = make_stego_image(cover, variant, key), make_stego_image(cover, variant, key)
    assert np.array_equal(np.array(first), np.array(second))
    assert not np.array_equal(np.array(first), np.array(cover))


def test_feature_table_shape_labels_and_finiteness(tmp_path):
    covers = generate_synthetic_covers(tmp_path / "covers", count=2)
    table = build_feature_table(covers, seed=5, variants=SMALL_VARIANTS)

    assert list(table.columns) == META_COLUMNS + FEATURE_NAMES
    assert len(table) == 2 * (1 + len(SMALL_VARIANTS))
    assert table["label"].tolist() == [0, 1, 1, 0, 1, 1]
    assert table["cover_id"].notna().all() and table["source_id"].notna().all()
    assert np.isfinite(table[FEATURE_NAMES].to_numpy()).all()


def test_feature_table_csv_is_byte_identical_for_same_seed(tmp_path):
    covers = generate_synthetic_covers(tmp_path / "covers", count=2)
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    write_feature_table(build_feature_table(covers, seed=9, variants=SMALL_VARIANTS), first)
    write_feature_table(build_feature_table(covers, seed=9, variants=SMALL_VARIANTS), second)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.slow
def test_parallel_workers_give_the_same_csv_as_one_worker(tmp_path):
    covers = generate_synthetic_covers(tmp_path / "covers", count=4)
    serial, parallel = tmp_path / "serial.csv", tmp_path / "parallel.csv"
    write_feature_table(build_feature_table(covers, seed=9, variants=SMALL_VARIANTS), serial)
    write_feature_table(build_feature_table(covers, seed=9, variants=SMALL_VARIANTS, workers=2), parallel)
    assert serial.read_bytes() == parallel.read_bytes()
