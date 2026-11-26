"""HTTP API tests: contract, failure modes, limits and security headers."""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.analysis import AnalysisService
from api.config import Settings
from api.main import create_app
from api.middleware import RateLimitMiddleware
from core.pipeline import max_message_bytes
from ml.risk import PreFlightRiskScorer

TEST_SETTINGS = Settings(static_dir=None, rate_limit_per_minute=0, max_concurrent_jobs=2, log_level="WARNING")
SECRET_PASSWORD = "correct horse battery staple"


def png_bytes(size: int = 96, seed: int = 0, mode: str = "RGB") -> bytes:
    rng = np.random.default_rng(seed)
    channels = {"RGB": 3, "RGBA": 4}[mode]
    pixels = rng.integers(0, 256, size=(size, size, channels), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels, mode=mode).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(size: int = 96) -> bytes:
    buffer = io.BytesIO()
    Image.open(io.BytesIO(png_bytes(size))).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def analysis(tiny_model_path) -> AnalysisService:
    return AnalysisService.load(tiny_model_path)


@pytest.fixture
def client(analysis) -> Iterator[TestClient]:
    with TestClient(create_app(TEST_SETTINGS, analysis)) as test_client:
        yield test_client


def make_client(analysis: AnalysisService | None = None, **overrides) -> TestClient:
    service = analysis or AnalysisService(None, PreFlightRiskScorer(), "No trained detector.")
    return TestClient(create_app(replace(TEST_SETTINGS, **overrides), service))


@pytest.fixture
def key_pair(client) -> dict:
    return client.post("/api/keys/generate", json={}).json()


def hide(client: TestClient, cover: bytes, **form) -> object:
    return client.post("/api/hide", files={"cover": ("holiday.png", cover, "image/png")}, data=form)


def reveal(client: TestClient, image: bytes, **form) -> object:
    return client.post("/api/reveal", files={"image": ("holiday.png", image, "image/png")}, data=form)


# --- meta -------------------------------------------------------------------------------------------


def test_health_reports_ok(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_reports_limits_and_available_detector(client):
    meta = client.get("/api/meta").json()

    assert meta["limits"]["max_upload_bytes"] == TEST_SETTINGS.max_upload_bytes
    assert meta["detector"]["available"] is True


def test_meta_explains_why_detector_is_unavailable():
    with make_client() as client:
        detector = client.get("/api/meta").json()["detector"]

    assert detector["available"] is False
    assert detector["unavailable_reason"] == "No trained detector."


# --- keys -------------------------------------------------------------------------------------------


def test_generated_key_pair_is_unencrypted_without_passphrase(key_pair):
    assert key_pair["private_key_pem"].startswith("-----BEGIN PRIVATE KEY-----")
    assert key_pair["is_private_key_encrypted"] is False


def test_generated_private_key_is_encrypted_with_passphrase(client):
    pair = client.post("/api/keys/generate", json={"passphrase": "s3cret"}).json()

    assert "ENCRYPTED" in pair["private_key_pem"]
    assert pair["is_private_key_encrypted"] is True


def test_inspect_returns_same_fingerprint_as_generation(client, key_pair):
    info = client.post("/api/keys/inspect", json={"public_key": key_pair["public_key_pem"]}).json()

    assert info["fingerprint"] == key_pair["fingerprint"]


def test_inspect_rejects_invalid_public_key(client):
    response = client.post("/api/keys/inspect", json={"public_key": "not a key"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_key"


# --- hide and reveal --------------------------------------------------------------------------------


@pytest.mark.parametrize("algorithm", ["replacement", "matching"])
def test_public_key_round_trip_recovers_message(client, key_pair, algorithm):
    stego = hide(
        client,
        png_bytes(),
        message="meet at noon ☀",
        method="public_key",
        recipient_public_key=key_pair["public_key_base64"],
        algorithm=algorithm,
    )

    revealed = reveal(client, stego.content, method="public_key", private_key=key_pair["private_key_pem"])

    assert revealed.json() == {"message": "meet at noon ☀", "encoding": "utf-8", "message_bytes": 16}


def test_password_round_trip_recovers_message(client):
    stego = hide(client, png_bytes(), message="hello", method="password", password=SECRET_PASSWORD)

    revealed = reveal(client, stego.content, method="password", password=SECRET_PASSWORD)

    assert revealed.json()["message"] == "hello"


def test_encrypted_private_key_round_trip_needs_passphrase(client):
    pair = client.post("/api/keys/generate", json={"passphrase": "s3cret"}).json()
    stego = hide(client, png_bytes(), message="hi", method="public_key", recipient_public_key=pair["public_key_pem"])

    revealed = reveal(
        client, stego.content, method="public_key", private_key=pair["private_key_pem"], passphrase="s3cret"
    )

    assert revealed.json()["message"] == "hi"


def test_hide_returns_png_named_after_cover_without_revealing_purpose(client, key_pair):
    response = hide(
        client, png_bytes(), message="x", method="public_key", recipient_public_key=key_pair["public_key_base64"]
    )

    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == 'attachment; filename="holiday.png"'


def test_hide_keeps_alpha_channel_of_rgba_cover(client, key_pair):
    response = hide(
        client,
        png_bytes(mode="RGBA"),
        message="x",
        method="public_key",
        recipient_public_key=key_pair["public_key_base64"],
    )

    assert Image.open(io.BytesIO(response.content)).mode == "RGBA"


def test_reveal_with_wrong_key_fails_closed(client, key_pair):
    other = client.post("/api/keys/generate", json={}).json()
    stego = hide(
        client, png_bytes(), message="x", method="public_key", recipient_public_key=key_pair["public_key_base64"]
    )

    response = reveal(client, stego.content, method="public_key", private_key=other["private_key_pem"])

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_message_found"
    assert "message" not in response.json()


def test_reveal_of_clean_image_reports_no_message(client, key_pair):
    response = reveal(client, png_bytes(), method="public_key", private_key=key_pair["private_key_pem"])

    assert response.json()["error"]["code"] == "no_message_found"


def test_reveal_rejects_jpeg_because_compression_destroys_message(client):
    response = client.post(
        "/api/reveal",
        files={"image": ("a.jpg", jpeg_bytes(), "image/jpeg")},
        data={"method": "password", "password": "x"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "lossy_image"


def test_reveal_rejects_unreadable_private_key(client):
    response = reveal(client, png_bytes(), method="public_key", private_key="-----BEGIN PRIVATE KEY-----\nAAAA")

    assert response.json()["error"] == {
        "code": "invalid_key",
        "message": response.json()["error"]["message"],
        "request_id": response.json()["error"]["request_id"],
        "field": "private_key",
    }


def test_hide_requires_password_for_password_method(client):
    response = hide(client, png_bytes(), message="x", method="password")

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "password"


def test_hide_reports_capacity_exceeded_with_numbers(client, key_pair):
    tiny_cover = png_bytes(size=8)

    response = hide(
        client, tiny_cover, message="x" * 500, method="public_key", recipient_public_key=key_pair["public_key_base64"]
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "capacity_exceeded"
    assert "500" in response.json()["error"]["message"]


def test_validation_error_never_echoes_submitted_secret(client):
    response = hide(client, png_bytes(), message="x", method="password", password=SECRET_PASSWORD, algorithm="bogus")

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "algorithm"
    assert SECRET_PASSWORD not in response.text


def test_message_over_limit_is_rejected_before_embedding(analysis):
    with make_client(analysis, max_message_bytes=10) as client:
        response = hide(client, png_bytes(), message="x" * 11, method="password", password="pw")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "message_too_long"


# --- uploads ----------------------------------------------------------------------------------------


def test_non_image_upload_is_rejected(client):
    response = client.post("/api/capacity", files={"image": ("notes.png", b"hello", "image/png")})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_image"


def test_unsupported_format_is_rejected(client):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="GIF")

    response = client.post("/api/capacity", files={"image": ("a.gif", buffer.getvalue(), "image/gif")})

    assert response.status_code == 415


def test_image_over_pixel_limit_is_rejected(analysis):
    with make_client(analysis, max_image_pixels=32 * 32) as client:
        response = client.post("/api/capacity", files={"image": ("a.png", png_bytes(size=64), "image/png")})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"


def test_request_body_over_limit_is_rejected(analysis):
    with make_client(analysis, max_upload_bytes=1024, max_message_bytes=0) as client:
        response = client.post("/api/capacity", files={"image": ("a.png", b"0" * 3 * 1024 * 1024, "image/png")})

    assert response.status_code == 413


# --- analysis ---------------------------------------------------------------------------------------


def test_capacity_matches_pipeline_for_both_methods(client):
    capacity = client.post("/api/capacity", files={"image": ("a.png", png_bytes(), "image/png")}).json()
    image = Image.open(io.BytesIO(png_bytes()))

    assert capacity["max_message_bytes"] == {
        "password": max_message_bytes(image, "password"),
        "public_key": max_message_bytes(image, "asymmetric"),
    }


def test_capacity_flags_jpeg_cover_as_lossy(client):
    capacity = client.post("/api/capacity", files={"image": ("a.jpg", jpeg_bytes(), "image/jpeg")}).json()

    assert capacity["is_lossy_source"] is True


def test_preflight_reports_risk_and_recommendation_within_capacity(client):
    response = client.post(
        "/api/preflight", files={"image": ("a.png", png_bytes(), "image/png")}, data={"message_bytes": "100"}
    ).json()

    assert response["risk"]["level"] in {"low", "medium", "high"}
    assert response["fits"] is True
    assert 0 <= response["recommended_max_message_bytes"] <= response["capacity"]["max_message_bytes"]["password"]


def test_preflight_flags_message_that_does_not_fit(client):
    response = client.post(
        "/api/preflight", files={"image": ("a.png", png_bytes(size=16), "image/png")}, data={"message_bytes": "5000"}
    ).json()

    assert response["fits"] is False


def test_detect_returns_probability_and_top_features(client):
    result = client.post("/api/detect", files={"image": ("a.png", png_bytes(), "image/png")}).json()

    assert 0.0 <= result["probability"] <= 1.0
    assert result["verdict"] in {"clean", "likely_clean", "suspicious", "stego"}
    assert len(result["top_features"]) > 0


def test_detect_without_trained_detector_returns_503():
    with make_client() as client:
        response = client.post("/api/detect", files={"image": ("a.png", png_bytes(), "image/png")})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "detector_unavailable"


# --- cross-cutting ----------------------------------------------------------------------------------


def test_api_responses_carry_security_headers_and_no_store(client):
    response = client.get("/api/meta")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_unknown_api_route_returns_json_404(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unexpected_error_returns_generic_500_without_details(analysis, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("internal secret detail")

    monkeypatch.setattr(analysis, "detect", explode)
    with TestClient(create_app(TEST_SETTINGS, analysis), raise_server_exceptions=False) as client:
        response = client.post("/api/detect", files={"image": ("a.png", png_bytes(), "image/png")})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "internal secret detail" not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


def test_rate_limit_rejects_requests_over_the_limit(analysis):
    with make_client(analysis, rate_limit_per_minute=2) as client:
        statuses = [client.post("/api/keys/generate", json={}).status_code for _ in range(3)]
        limited = client.post("/api/keys/generate", json={})

    assert statuses == [200, 200, 429]
    assert int(limited.headers["retry-after"]) >= 1


def test_rate_limit_window_slides_with_time():
    now = [0.0]
    limiter = RateLimitMiddleware(app=None, requests_per_minute=1, clock=lambda: now[0])

    first = limiter._record_and_get_retry_after("client")
    blocked = limiter._record_and_get_retry_after("client")
    now[0] = 61.0
    after_window = limiter._record_and_get_retry_after("client")

    assert (first, after_window) == (0, 0)
    assert blocked > 0


def test_front_end_routes_fall_back_to_index_html(analysis, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>StegoShield</title>")
    (tmp_path / "assets" / "app-1234.js").write_text("console.log(1)")

    with make_client(analysis, static_dir=tmp_path) as client:
        page = client.get("/reveal")
        asset = client.get("/assets/app-1234.js")
        api_miss = client.get("/api/missing")

    assert "StegoShield" in page.text
    assert page.headers["cache-control"] == "no-cache"
    assert "immutable" in asset.headers["cache-control"]
    assert api_miss.status_code == 404
    assert api_miss.headers["content-type"] == "application/json"
