"""Safe decoding of uploaded images: size, pixel and format limits, and carrier-mode normalisation."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from api.config import Settings
from api.errors import ApiError

COVER_FORMATS = frozenset({"PNG", "JPEG", "BMP", "WEBP"})
LOSSLESS_FORMATS = frozenset({"PNG", "BMP"})
CARRIER_MODES = frozenset({"RGB", "RGBA", "L"})
DEFAULT_DOWNLOAD_STEM = "image"
MAX_DOWNLOAD_STEM_LENGTH = 64


@dataclass(frozen=True)
class UploadedImage:
    """A decoded upload, already converted to a mode the embedding engine accepts."""

    image: Image.Image
    source_format: str
    filename: str

    @property
    def is_lossy(self) -> bool:
        return self.source_format not in LOSSLESS_FORMATS


async def load_cover_image(upload: UploadFile, settings: Settings) -> UploadedImage:
    """Decode an image to hide a message in or to analyse. Lossy formats are accepted here.

    Raises:
        ApiError: The upload is too large, not an image, or an unsupported format.
    """
    return await _load_image(upload, settings)


async def load_stego_image(upload: UploadFile, settings: Settings) -> UploadedImage:
    """Decode an image to reveal a message from. Only lossless formats can still hold one.

    Raises:
        ApiError: As for load_cover_image, or the image is lossy (e.g. JPEG).
    """
    uploaded = await _load_image(upload, settings)
    if uploaded.is_lossy:
        raise ApiError(
            422,
            "lossy_image",
            f"This image is a {uploaded.source_format} file. Lossy compression destroys hidden data, "
            "so nothing can be recovered. Use the original PNG you received.",
            field="image",
        )
    return uploaded


def encode_png(image: Image.Image) -> bytes:
    """Serialise an image as PNG without any metadata from the original upload."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def download_filename(original_filename: str) -> str:
    """Name the output after the cover so the file name doesn't announce a hidden message."""
    stem = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-.")[:MAX_DOWNLOAD_STEM_LENGTH]
    return f"{safe_stem or DEFAULT_DOWNLOAD_STEM}.png"


async def _load_image(upload: UploadFile, settings: Settings) -> UploadedImage:
    data = await upload.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise ApiError(413, "image_too_large", f"The image is larger than the {limit_mb} MB limit.", field="image")
    if not data:
        raise ApiError(400, "invalid_image", "The uploaded file is empty.", field="image")

    image = _open_image(data)
    _check_format(image)
    _check_pixel_count(image, settings.max_image_pixels)
    _decode_pixels(image)
    return UploadedImage(
        image=_to_carrier_mode(image),
        source_format=image.format or "UNKNOWN",
        filename=upload.filename or DEFAULT_DOWNLOAD_STEM,
    )


def _open_image(data: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError(400, "invalid_image", "This file isn't a readable image.", field="image") from exc


def _check_format(image: Image.Image) -> None:
    if image.format not in COVER_FORMATS:
        allowed = ", ".join(sorted(COVER_FORMATS))
        raise ApiError(
            415,
            "unsupported_format",
            f"{image.format or 'This'} images aren't supported. Use one of: {allowed}.",
            field="image",
        )


def _check_pixel_count(image: Image.Image, max_pixels: int) -> None:
    # Checked before decoding, so an oversized image never gets loaded into memory.
    width, height = image.size
    if width * height > max_pixels:
        raise ApiError(
            413,
            "image_too_large",
            f"The image is {width}×{height} pixels; the limit is {max_pixels:,} pixels in total.",
            field="image",
        )


def _decode_pixels(image: Image.Image) -> None:
    try:
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ApiError(400, "invalid_image", "The image file is damaged or truncated.", field="image") from exc


def _to_carrier_mode(image: Image.Image) -> Image.Image:
    if image.mode in CARRIER_MODES:
        return image
    has_alpha = image.mode in ("LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    return image.convert("RGBA" if has_alpha else "RGB")
