"""Evaluation Lab live sample run: built-in samples, the run endpoint, and the changed-value map."""

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
from api.lab_samples import change_map, load_samples, message_bytes_for_share
from api.main import create_app
from experiments.common import load_split

TEST_SETTINGS = Settings(static_dir=None, rate_limit_per_minute=0, max_concurrent_jobs=2, log_level="WARNING")


@pytest.fixture(scope="module")
def client(tiny_model_path) -> Iterator[TestClient]:
    with TestClient(create_app(TEST_SETTINGS, AnalysisService.load(tiny_model_path))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def boat_run(client) -> dict:
    """One 10 % run on a built-in photo, shared by the tests that only read its result."""
    response = client.post("/api/lab/samples/03-boat/run", json={"payload_percent": 10})
    assert response.status_code == 200
    return response.json()


def decode_data_url(url: str) -> Image.Image:
    header, payload = url.split(",", 1)
    assert header in ("data:image/png;base64", "data:image/jpeg;base64")
    return Image.open(io.BytesIO(base64.b64decode(payload)))


# --- the bundled samples ------------------------------------------------------------------------------


def test_eight_samples_ordered_smooth_to_textured():
    samples = load_samples()

    assert len(samples) == 8
    assert [s.texture_complexity for s in samples] == sorted(s.texture_complexity for s in samples)
    assert {s.texture.value for s in samples} == {"smooth", "medium", "textured"}


def test_every_sample_file_is_a_512px_rgb_png():
    for sample in load_samples():
        with Image.open(sample.path) as image:
            assert (image.format, image.size) == ("PNG", (512, 512))


def test_every_sample_comes_from_the_detectors_held_out_split():
    """The live run would overstate the detector if it scored photos it was trained on."""
    split = load_split()
    test_side = set(split.loc[split["side"] == "test", "cover_id"])

    assert {sample.source_cover_id for sample in load_samples()} <= test_side


def test_samples_come_from_different_photos():
    sources = [sample.source_cover_id.split("_")[0] for sample in load_samples()]

    assert len(set(sources)) == len(sources)


# --- endpoints ---------------------------------------------------------------------------------------


def test_list_samples_links_each_image(client):
    listing = client.get("/api/lab/samples").json()

    assert len(listing["samples"]) == 8
    assert "DIV2K" in listing["source"]
    first = listing["samples"][0]
    image = client.get(first["image_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def test_unknown_sample_returns_404(client):
    response = client.get("/api/lab/samples/not-a-sample/image")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_sample"


def test_run_reports_both_algorithms_with_previews(boat_run):
    run = boat_run
    assert [result["algorithm"] for result in run["results"]] == ["replacement", "matching"]
    for result in run["results"]:
        assert 0 <= result["predicted_probability"] <= 1
        assert result["is_detected"] == (result["actual_probability"] >= run["threshold"])
        assert result["psnr_db"] > 50
        assert 0 < result["changed_share"] < 0.1
        assert decode_data_url(result["stego_preview"]).size == (256, 256)
        assert decode_data_url(result["change_map"]).size == (128, 128)


def test_run_hides_the_requested_share(boat_run):
    assert boat_run["message_bytes"] == 512 * 512 * 3 // 10 // 8 - 64


@pytest.mark.parametrize("payload_percent", [0, 0.5, 51, 100])
def test_run_rejects_payload_outside_1_to_50_percent(client, payload_percent):
    response = client.post("/api/lab/samples/03-boat/run", json={"payload_percent": payload_percent})

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "payload_percent"


def test_run_without_a_detector_returns_503():
    service = AnalysisService(None, "No trained detector.")
    with TestClient(create_app(replace(TEST_SETTINGS), service)) as client:
        response = client.post("/api/lab/samples/03-boat/run", json={"payload_percent": 10})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "detector_unavailable"


# --- helpers -----------------------------------------------------------------------------------------


def test_message_size_never_exceeds_capacity_or_drops_below_one_byte():
    cover = Image.new("RGB", (64, 64))

    assert message_bytes_for_share(cover, 1) == 1
    assert message_bytes_for_share(cover, 50) == 64 * 64 * 3 // 2 // 8 - 64


def test_change_map_is_a_full_resolution_centre_crop_in_channel_colours():
    changed = np.zeros((512, 512, 3), dtype=bool)
    changed[200, 300, 1] = True  # one green value inside the centre crop (rows/cols 192-319)
    changed[10, 10, 0] = True  # one red value outside it

    pixels = np.asarray(change_map(changed))

    assert pixels.shape == (128, 128, 3)
    assert pixels[200 - 192, 300 - 192].tolist() == [0, 255, 0]
    assert pixels.sum() == 255
