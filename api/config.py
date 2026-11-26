"""Runtime settings, read once from STEGOSHIELD_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_PREFIX = "STEGOSHIELD_"
MEBIBYTE = 1024 * 1024

DEFAULT_MAX_UPLOAD_BYTES = 10 * MEBIBYTE
DEFAULT_MAX_IMAGE_PIXELS = 4096 * 4096
DEFAULT_MAX_MESSAGE_BYTES = 512 * 1024
DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_STATIC_DIR = Path("frontend/dist")


@dataclass(frozen=True)
class Settings:
    """Limits and switches for one running API instance."""

    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    max_concurrent_jobs: int = os.cpu_count() or 4
    cors_origins: tuple[str, ...] = ()
    static_dir: Path | None = DEFAULT_STATIC_DIR
    detector_path: Path | None = None
    enable_docs: bool = True
    enable_hsts: bool = False
    log_level: str = "INFO"

    @property
    def max_request_bytes(self) -> int:
        """Whole-request ceiling: one image plus message text and form overhead."""
        return self.max_upload_bytes + self.max_message_bytes + MEBIBYTE

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from the environment, falling back to the defaults above."""
        return cls(
            max_upload_bytes=_env_int("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_BYTES // MEBIBYTE) * MEBIBYTE,
            max_image_pixels=_env_int("MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS),
            max_message_bytes=_env_int("MAX_MESSAGE_BYTES", DEFAULT_MAX_MESSAGE_BYTES),
            rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE),
            max_concurrent_jobs=_env_int("MAX_CONCURRENT_JOBS", os.cpu_count() or 4),
            cors_origins=_env_list("CORS_ORIGINS"),
            static_dir=_env_path("STATIC_DIR", DEFAULT_STATIC_DIR),
            detector_path=_env_path("DETECTOR_PATH", None),
            enable_docs=_env_bool("ENABLE_DOCS", True),
            enable_hsts=_env_bool("ENABLE_HSTS", False),
            log_level=os.environ.get(ENV_PREFIX + "LOG_LEVEL", "INFO").upper(),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{ENV_PREFIX}{name} must be an integer, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.environ.get(ENV_PREFIX + name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_path(name: str, default: Path | None) -> Path | None:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return default
    return Path(raw) if raw.strip() else None
