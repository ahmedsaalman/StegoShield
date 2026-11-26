"""Tests for the Evaluation Lab endpoints (/api/lab/*)."""

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.analysis import AnalysisService
from api.errors import ApiError
from api.lab import LAB_MAX_PIXELS, lab_results
from api.main import create_app
from tests.test_api import TEST_SETTINGS, png_bytes


def upload(data: bytes, name: str = "a.png") -> dict:
    return {"image": (name, data, "image/png")}


@pytest.fixture(scope="module")
def client(tiny_model_path) -> Iterator[TestClient]:
    with TestClient(create_app(TEST_SETTINGS, AnalysisService.load(tiny_model_path))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def client_without_detector() -> Iterator[TestClient]:
    with TestClient(create_app(TEST_SETTINGS, AnalysisService(None, "No trained detector."))) as test_client:
        yield test_client


def test_saved_results_summarise_every_experiment(client):
    results = client.get("/api/lab/results").json()

    assert results["held_out_covers"] == 100
    assert len(results["detector"]) == 16
    assert {row["predicted_level"] for row in results["preflight_validity"]} == {"low", "medium", "high"}
    assert [row["transport"] for row in results["robustness"]] == ["png_resave", "jpeg_q90", "jpeg_q75", "resize_50"]
    assert len(results["quality"]) == 8


def test_missing_results_files_raise_a_503_error(tmp_path):
    with pytest.raises(ApiError) as raised:
        lab_results(tmp_path)

    assert raised.value.status_code == 503
    assert raised.value.code == "lab_results_unavailable"


def test_quality_demo_reports_every_share_and_algorithm(client):
    points = client.post("/api/lab/quality", files=upload(png_bytes())).json()["points"]

    assert len(points) == 8
    assert all(point["psnr_db"] > 40 and point["ssim"] > 0.9 for point in points)


def test_robustness_demo_recovers_png_and_fails_safely_otherwise(client):
    trials = client.post("/api/lab/robustness", files=upload(png_bytes())).json()["trials"]

    outcomes = {trial["transport"]: trial["outcome"] for trial in trials}
    assert outcomes == {
        "png_resave": "recovered",
        "jpeg_q90": "failed_safely",
        "jpeg_q75": "failed_safely",
        "resize_50": "failed_safely",
    }


def test_attack_demo_only_recovers_the_control(client):
    trials = client.post("/api/lab/attacks", files=upload(png_bytes())).json()["trials"]

    outcomes = {trial["attack"]: trial["outcome"] for trial in trials}
    assert outcomes.pop("control") == "recovered"
    assert set(outcomes.values()) == {"failed_safely"}
    assert all(trial["description"] for trial in trials)


def test_detector_comparison_scores_clean_and_every_variant(client):
    result = client.post("/api/lab/detector-comparison", files=upload(png_bytes())).json()

    assert 0 <= result["clean_probability"] <= 1
    assert len(result["points"]) == 8
    assert all(point["is_detected"] == (point["probability"] >= result["threshold"]) for point in result["points"])


def test_detector_comparison_without_detector_returns_503(client_without_detector):
    response = client_without_detector.post("/api/lab/detector-comparison", files=upload(png_bytes()))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "detector_unavailable"


def test_lab_rejects_images_over_its_pixel_limit(client):
    buffer = io.BytesIO()
    Image.new("RGB", (1024, LAB_MAX_PIXELS // 1024 + 1)).save(buffer, format="PNG")

    response = client.post("/api/lab/quality", files=upload(buffer.getvalue()))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"
