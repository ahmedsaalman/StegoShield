"""Evaluation Lab: hide each built-in sample text in the user's image and show what it is exposed to.

For one text and each embedding algorithm: the pre-flight prediction, the detector's score on the
real stego image and its strongest signals, visual quality, five live safety checks (right key,
wrong key, bit flips, JPEG, resize), and an exposure map of the user's own image.

The exposure map explains, it does not decide: the detector scores the whole image at once. The map
shows where the changes went (cyan) and which parts of the image are flattest (red), because ±1
changes stand out most against smooth areas; the hotspot is the flat area that took the most changes.
"""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass
from functools import partial

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from api.errors import ApiError
from api.lab import prepare_lab_image
from api.sample_texts import SAMPLE_TEXTS, SampleText, find_sample_text
from api.schemas import (
    EmbeddingAlgorithmChoice,
    LabMessageRunResponse,
    LabOutcome,
    LabSampleText,
    LabSampleTextsResponse,
    MessageAlgorithmResult,
    MessageCheck,
    PixelBox,
    RiskLevel,
    SignalFeature,
)
from core.crypto import MODE_ASYMMETRIC, packet_overhead
from core.keys import generate_keypair
from core.pipeline import max_message_bytes, stego_decode_asymmetric, stego_encode_asymmetric
from experiments.attacks import Attack, tamper_image
from experiments.quality import measure_quality
from experiments.robustness import Transport, apply_transport, reveal_outcome
from ml.dataset import DEFAULT_SEED
from ml.detector import StegoDetector
from ml.risk import PreflightChecker

KEY_MODE = "asymmetric"
ALGORITHMS = (EmbeddingAlgorithmChoice.REPLACEMENT, EmbeddingAlgorithmChoice.MATCHING)
SLOTS_PER_PIXEL = 3
BLOCK_PX = 16
FLAT_QUANTILE = 1 / 3
OVERVIEW_MAX_PX = 448
HOTSPOT_PX = 64
OVERVIEW_JPEG_QUALITY = 80
DIM_FACTOR = 0.45
FLAT_TINT_ALPHA = 0.4
TOP_SIGNALS = 3
LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114])
CYAN = np.array([0, 229, 255], dtype=np.float64)
RED = np.array([255, 59, 48], dtype=np.float64)
YELLOW = (255, 214, 10)
UNKNOWN_TEXT_MESSAGE = "There is no built-in sample message with that id."
DETECTOR_UNAVAILABLE_MESSAGE = "The detector isn't installed on this server yet, so messages can't be scored."

# (check id, label, expected outcome). Everything except the right key must fail safely.
CHECKS = (
    ("right_key", "Reveal with the right private key", LabOutcome.RECOVERED),
    ("wrong_key", "Reveal with someone else's private key", LabOutcome.FAILED_SAFELY),
    ("bit_flips", "Flip half of the lowest bits, then reveal", LabOutcome.FAILED_SAFELY),
    ("jpeg_q90", "Re-save as JPEG (quality 90), then reveal", LabOutcome.FAILED_SAFELY),
    ("resize_50", "Resize to 50 %, then reveal", LabOutcome.FAILED_SAFELY),
)


@dataclass(frozen=True)
class ExposureMap:
    """Where the changes went relative to the image's texture, block by block."""

    block_px: int
    flat_blocks: np.ndarray  # bool, (rows, cols)
    flat_area_share: float
    flat_change_share: float
    hotspot: tuple[int, int, int, int] | None  # x, y, width, height in pixels


def list_texts() -> LabSampleTextsResponse:
    """Every built-in sample message, full text included."""
    return LabSampleTextsResponse(
        texts=[
            LabSampleText(id=s.id, title=s.title, description=s.description, size_bytes=s.size_bytes, text=s.text)
            for s in SAMPLE_TEXTS
        ]
    )


def run_message(image: Image.Image, text_id: str, detector: StegoDetector | None) -> LabMessageRunResponse:
    """Hide one sample text in the image with each algorithm and measure what it is exposed to.

    Raises:
        ApiError: Unknown text (404), no detector (503) or an image over the Lab size cap (413).
    """
    sample = _find_text(text_id)
    if detector is None:
        raise ApiError(503, "detector_unavailable", DETECTOR_UNAVAILABLE_MESSAGE)
    cover = prepare_lab_image(image)
    message = sample.text.encode("utf-8")
    capacity = max_message_bytes(cover, KEY_MODE)
    total_slots = cover.width * cover.height * SLOTS_PER_PIXEL
    payload_percent = round(100 * (len(message) + packet_overhead(MODE_ASYMMETRIC)) * 8 / total_slots, 2)
    fits = len(message) <= capacity
    results = []
    if fits:
        checker = PreflightChecker(detector, seed=DEFAULT_SEED)
        results = [_measure(cover, message, algorithm, checker, detector) for algorithm in ALGORITHMS]
    return LabMessageRunResponse(
        text_id=sample.id,
        title=sample.title,
        message_bytes=len(message),
        capacity_bytes=capacity,
        fits=fits,
        payload_percent=min(payload_percent, 100.0),
        threshold=detector.threshold,
        image_width=cover.width,
        image_height=cover.height,
        results=results,
    )


def exposure_map(cover_pixels: np.ndarray, changed_pixels: np.ndarray, block_px: int = BLOCK_PX) -> ExposureMap:
    """Split the image into blocks, mark its flattest third, and find the flat block with most changes."""
    height, width = changed_pixels.shape
    block = max(1, min(block_px, height, width))
    rows, cols = height // block, width // block
    texture = np.abs(ndimage.laplace(cover_pixels.astype(np.float64) @ LUMA_WEIGHTS))
    block_texture = _block_reduce(texture, block, rows, cols).mean(axis=(1, 3))
    block_changes = _block_reduce(changed_pixels, block, rows, cols).sum(axis=(1, 3))
    flat = block_texture <= np.quantile(block_texture, FLAT_QUANTILE)
    total_changes = int(block_changes.sum())
    flat_changes = int(block_changes[flat].sum())
    return ExposureMap(
        block_px=block,
        flat_blocks=flat,
        flat_area_share=float(flat.mean()),
        flat_change_share=flat_changes / total_changes if total_changes else 0.0,
        hotspot=_hotspot(np.where(flat, block_changes, 0), block, width, height),
    )


def overview_image(cover_pixels: np.ndarray, changed_pixels: np.ndarray, exposure: ExposureMap) -> Image.Image:
    """Dimmed greyscale image; flat blocks tinted red, changed pixels cyan, hotspot boxed in yellow."""
    height, width = changed_pixels.shape
    grey = (cover_pixels.astype(np.float64) @ LUMA_WEIGHTS) * DIM_FACTOR
    canvas = np.repeat(grey[..., None], 3, axis=2)
    flat_mask = np.zeros((height, width), dtype=bool)
    expanded = np.kron(exposure.flat_blocks, np.ones((exposure.block_px, exposure.block_px), dtype=bool))
    flat_mask[: expanded.shape[0], : expanded.shape[1]] = expanded
    canvas[flat_mask] = canvas[flat_mask] * (1 - FLAT_TINT_ALPHA) + RED * FLAT_TINT_ALPHA
    canvas[changed_pixels] = CYAN
    image = Image.fromarray(canvas.clip(0, 255).astype(np.uint8), "RGB")
    if exposure.hotspot:
        x, y, w, h = exposure.hotspot
        line = max(2, round(max(width, height) / 256))
        ImageDraw.Draw(image).rectangle((x, y, x + w - 1, y + h - 1), outline=YELLOW, width=line)
    # Nearest-neighbour keeps the share of cyan pixels honest; averaging would blur it away.
    image.thumbnail((OVERVIEW_MAX_PX, OVERVIEW_MAX_PX), Image.Resampling.NEAREST)
    return image


def _measure(
    cover: Image.Image,
    message: bytes,
    algorithm: EmbeddingAlgorithmChoice,
    checker: PreflightChecker,
    detector: StegoDetector,
) -> MessageAlgorithmResult:
    private_key, public_key = generate_keypair()
    predicted = checker.predict_risk(cover, len(message), key_mode=KEY_MODE, algorithm=algorithm.value)
    stego = stego_encode_asymmetric(cover, message, public_key, algorithm=algorithm.value)
    detection = detector.predict(stego)
    quality = measure_quality(cover, stego)
    cover_pixels = np.asarray(cover)
    changed_values = np.asarray(stego.convert("RGB")) != cover_pixels
    changed_pixels = changed_values.any(axis=2)
    exposure = exposure_map(cover_pixels, changed_pixels)
    hotspot_original, hotspot_stego = _hotspot_crops(cover_pixels, changed_pixels, exposure.hotspot)
    return MessageAlgorithmResult(
        algorithm=algorithm,
        predicted_probability=min(1.0, max(0.0, predicted.probability)),
        predicted_level=RiskLevel(predicted.level.value),
        actual_probability=min(1.0, max(0.0, detection.probability)),
        is_detected=detection.is_stego,
        psnr_db=quality.psnr_db if math.isfinite(quality.psnr_db) else None,
        ssim=quality.ssim,
        changed_values=int(changed_values.sum()),
        changed_pixels=int(changed_pixels.sum()),
        flat_area_share=exposure.flat_area_share,
        flat_change_share=exposure.flat_change_share,
        hotspot=PixelBox(
            x=exposure.hotspot[0], y=exposure.hotspot[1], width=exposure.hotspot[2], height=exposure.hotspot[3]
        )
        if exposure.hotspot
        else None,
        checks=run_checks(stego, message, private_key),
        top_signals=[
            SignalFeature(feature=item.feature, z_score=item.z_score)
            for item in detection.top_features[:TOP_SIGNALS]
            if math.isfinite(item.z_score)
        ],
        overview_image=_data_url(overview_image(cover_pixels, changed_pixels, exposure), "JPEG"),
        hotspot_original=hotspot_original,
        hotspot_stego=hotspot_stego,
    )


def run_checks(stego: Image.Image, message: bytes, private_key: object) -> list[MessageCheck]:
    """Right key must recover the exact message; every other check must fail safely."""
    reveal = partial(stego_decode_asymmetric, recipient_private_key=private_key)
    other_private_key, _ = generate_keypair()
    trials = {
        "right_key": (reveal, stego),
        "wrong_key": (partial(stego_decode_asymmetric, recipient_private_key=other_private_key), stego),
        "bit_flips": (reveal, tamper_image(stego, Attack.FLIP_LSBS, DEFAULT_SEED)),
        "jpeg_q90": (reveal, apply_transport(stego, Transport.JPEG_Q90)),
        "resize_50": (reveal, apply_transport(stego, Transport.RESIZE_50)),
    }
    checks = []
    for check_id, label, expected in CHECKS:
        decode, received = trials[check_id]
        outcome = LabOutcome(reveal_outcome(decode, received, message).value)
        checks.append(MessageCheck(check=check_id, label=label, expected=expected, outcome=outcome))
    return checks


def _find_text(text_id: str) -> SampleText:
    sample = find_sample_text(text_id)
    if sample is None:
        raise ApiError(404, "unknown_text", UNKNOWN_TEXT_MESSAGE)
    return sample


def _block_reduce(values: np.ndarray, block: int, rows: int, cols: int) -> np.ndarray:
    return values[: rows * block, : cols * block].reshape(rows, block, cols, block)


def _hotspot(flat_changes: np.ndarray, block: int, width: int, height: int) -> tuple[int, int, int, int] | None:
    if flat_changes.size == 0 or flat_changes.max() == 0:
        return None
    row, col = np.unravel_index(int(np.argmax(flat_changes)), flat_changes.shape)
    side_x, side_y = min(HOTSPOT_PX, width), min(HOTSPOT_PX, height)
    centre_x, centre_y = col * block + block // 2, row * block + block // 2
    x = int(min(max(0, centre_x - side_x // 2), width - side_x))
    y = int(min(max(0, centre_y - side_y // 2), height - side_y))
    return x, y, side_x, side_y


def _hotspot_crops(
    cover_pixels: np.ndarray, changed_pixels: np.ndarray, hotspot: tuple[int, int, int, int] | None
) -> tuple[str | None, str | None]:
    if hotspot is None:
        return None, None
    x, y, w, h = hotspot
    original = cover_pixels[y : y + h, x : x + w]
    highlighted = original.astype(np.float64).copy()
    highlighted[changed_pixels[y : y + h, x : x + w]] = CYAN
    return (
        _data_url(Image.fromarray(original, "RGB"), "PNG"),
        _data_url(Image.fromarray(highlighted.astype(np.uint8), "RGB"), "PNG"),
    )


def _data_url(image: Image.Image, image_format: str) -> str:
    buffer = io.BytesIO()
    options = {"quality": OVERVIEW_JPEG_QUALITY} if image_format == "JPEG" else {"optimize": True}
    image.save(buffer, format=image_format, **options)
    mime = "image/jpeg" if image_format == "JPEG" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
