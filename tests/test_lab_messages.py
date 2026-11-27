"""Evaluation Lab message run: built-in sample texts hidden in the user's image, plus the exposure map."""

from __future__ import annotations

import base64
import io
from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.analysis import AnalysisService
from api.config import Settings
from api.lab_messages import CHECKS, HOTSPOT_PX, OVERVIEW_MAX_PX, exposure_map, overview_image
from api.lab_samples import find_sample
from api.main import create_app
from api.sample_texts import SAMPLE_TEXTS, find_sample_text

TEST_SETTINGS = Settings(static_dir=None, rate_limit_per_minute=0, max_concurrent_jobs=2, log_level="WARNING")
CYAN = (0, 229, 255)
PHOTO_PX = 256


@pytest.fixture(scope="module")
def client(tiny_model_path) -> Iterator[TestClient]:
    with TestClient(create_app(TEST_SETTINGS, AnalysisService.load(tiny_model_path))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def photo_png() -> bytes:
    """A 256 px crop of a real held-out photo, uploaded as if it were the user's own image."""
    with Image.open(find_sample("03-boat").path) as photo:
        return png_bytes(photo.convert("RGB").crop((128, 128, 128 + PHOTO_PX, 128 + PHOTO_PX)))


@pytest.fixture(scope="module")
def email_run(client, photo_png) -> dict:
    response = client.post("/api/lab/messages/email/run", files=upload(photo_png))
    assert response.status_code == 200
    return response.json()


def upload(png: bytes) -> dict:
    return {"image": ("photo.png", png, "image/png")}


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def decode_data_url(url: str) -> Image.Image:
    header, payload = url.split(",", 1)
    assert header in ("data:image/png;base64", "data:image/jpeg;base64")
    return Image.open(io.BytesIO(base64.b64decode(payload))).convert("RGB")


# --- the sample texts --------------------------------------------------------------------------------


def test_sample_texts_have_unique_ids_and_grow_in_size():
    sizes = [text.size_bytes for text in SAMPLE_TEXTS]

    assert len({text.id for text in SAMPLE_TEXTS}) == len(SAMPLE_TEXTS) == 6
    assert sizes == sorted(sizes)
    assert sizes[0] < 100 < 30_000 < sizes[-1]


def test_find_sample_text_returns_none_for_an_unknown_id():
    assert find_sample_text("email") is not None
    assert find_sample_text("nope") is None


def test_list_texts_includes_the_full_text(client):
    texts = client.get("/api/lab/messages").json()["texts"]

    assert [text["id"] for text in texts] == [text.id for text in SAMPLE_TEXTS]
    for listed, sample in zip(texts, SAMPLE_TEXTS, strict=True):
        assert listed["text"] == sample.text
        assert listed["size_bytes"] == len(sample.text.encode("utf-8"))


# --- running a message in the user's image -----------------------------------------------------------


def test_run_reports_both_algorithms_for_the_users_image(email_run):
    assert email_run["fits"] is True
    assert (email_run["image_width"], email_run["image_height"]) == (PHOTO_PX, PHOTO_PX)
    assert email_run["message_bytes"] == find_sample_text("email").size_bytes
    assert 0 < email_run["payload_percent"] < 5
    assert [result["algorithm"] for result in email_run["results"]] == ["replacement", "matching"]
    for result in email_run["results"]:
        assert result["is_detected"] == (result["actual_probability"] >= email_run["threshold"])
        assert result["psnr_db"] > 50
        assert 0 < result["changed_pixels"] <= result["changed_values"]


def test_every_safety_check_has_its_expected_outcome(email_run):
    expected = [(check, outcome.value) for check, _, outcome in CHECKS]
    for result in email_run["results"]:
        assert [(c["check"], c["expected"]) for c in result["checks"]] == expected
        assert all(c["outcome"] == c["expected"] for c in result["checks"])


def test_highlights_cover_the_users_image(email_run):
    for result in email_run["results"]:
        overview = decode_data_url(result["overview_image"])
        assert max(overview.size) <= OVERVIEW_MAX_PX
        assert 0.2 < result["flat_area_share"] < 0.45
        assert 0 <= result["flat_change_share"] <= 1

        hotspot = result["hotspot"]
        assert hotspot["x"] >= 0 and hotspot["y"] >= 0
        assert hotspot["x"] + hotspot["width"] <= PHOTO_PX and hotspot["y"] + hotspot["height"] <= PHOTO_PX
        assert decode_data_url(result["hotspot_original"]).size == (hotspot["width"], hotspot["height"])
        assert decode_data_url(result["hotspot_stego"]).size == (HOTSPOT_PX, HOTSPOT_PX)


def test_top_signals_are_the_strongest_detector_features(email_run):
    for result in email_run["results"]:
        signals = result["top_signals"]
        assert 1 <= len(signals) <= 3
        assert all(isinstance(signal["feature"], str) and signal["feature"] for signal in signals)


def test_message_too_large_for_the_image_is_reported_not_hidden(client):
    tiny = Image.fromarray(np.random.default_rng(0).integers(0, 256, (32, 32, 3), dtype=np.uint8), "RGB")
    run = client.post("/api/lab/messages/dossier/run", files=upload(png_bytes(tiny))).json()

    assert run["fits"] is False
    assert run["message_bytes"] > run["capacity_bytes"]
    assert run["payload_percent"] == 100
    assert run["results"] == []


def test_unknown_text_returns_404(client, photo_png):
    response = client.post("/api/lab/messages/nope/run", files=upload(photo_png))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_text"


def test_image_over_the_lab_cap_returns_413(client):
    large = Image.new("RGB", (1100, 1000), (120, 120, 120))
    response = client.post("/api/lab/messages/note/run", files=upload(png_bytes(large)))

    assert response.status_code == 413


def test_run_without_a_detector_returns_503(photo_png):
    service = AnalysisService(None, "No trained detector.")
    with TestClient(create_app(replace(TEST_SETTINGS), service)) as client:
        response = client.post("/api/lab/messages/note/run", files=upload(photo_png))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "detector_unavailable"


# --- exposure map ------------------------------------------------------------------------------------


def half_flat_cover(size: int = 64) -> np.ndarray:
    """Left half a flat grey, right half noise."""
    rng = np.random.default_rng(1)
    cover = np.full((size, size, 3), 128, dtype=np.uint8)
    cover[:, size // 2 :] = rng.integers(0, 256, (size, size // 2, 3), dtype=np.uint8)
    return cover


def test_exposure_map_marks_the_flat_side_and_its_busiest_block():
    cover = half_flat_cover()
    changed = np.zeros((64, 64), dtype=bool)
    changed[20:24, 4:8] = True  # 16 changes in a flat block
    changed[40:42, 40:42] = True  # 4 changes in a textured block

    exposure = exposure_map(cover, changed, block_px=16)

    assert exposure.flat_blocks[:, 0].all()  # the flattest third lies on the left
    assert not exposure.flat_blocks[:, 2:].any()
    assert exposure.flat_change_share == pytest.approx(16 / 20)
    x, y, w, h = exposure.hotspot
    assert x <= 4 and x + w >= 8 and y <= 20 and y + h >= 24


def test_exposure_map_without_changes_has_no_hotspot():
    exposure = exposure_map(half_flat_cover(), np.zeros((64, 64), dtype=bool))

    assert exposure.hotspot is None
    assert exposure.flat_change_share == 0


def test_overview_paints_changed_pixels_cyan_and_shrinks_large_images():
    cover = np.full((900, 600, 3), 128, dtype=np.uint8)
    changed = np.zeros((900, 600), dtype=bool)
    changed[::2, ::2] = True

    image = overview_image(cover, changed, exposure_map(cover, changed))

    assert max(image.size) == OVERVIEW_MAX_PX
    assert CYAN in {pixel for _, pixel in image.getcolors(maxcolors=1 << 16)}


def test_overview_keeps_unchanged_pixels_dimmed():
    cover = np.full((64, 64, 3), 200, dtype=np.uint8)
    changed = np.zeros((64, 64), dtype=bool)

    pixels = np.asarray(overview_image(cover, changed, exposure_map(cover, changed)))

    assert pixels.max() < 200
