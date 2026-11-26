"""Liveness and the public configuration the front end needs (limits, detector status)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api import __version__
from api.analysis import AnalysisService
from api.config import Settings
from api.dependencies import get_analysis, get_settings
from api.schemas import HealthResponse, Limits, MetaResponse

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    """Liveness probe for load balancers and container health checks."""
    return HealthResponse()


@router.get("/meta", response_model=MetaResponse)
def read_meta(
    settings: Annotated[Settings, Depends(get_settings)],
    analysis: Annotated[AnalysisService, Depends(get_analysis)],
) -> MetaResponse:
    """Version, upload limits and whether the detector is trained."""
    return MetaResponse(
        version=__version__,
        limits=Limits(
            max_upload_bytes=settings.max_upload_bytes,
            max_image_pixels=settings.max_image_pixels,
            max_message_bytes=settings.max_message_bytes,
            rate_limit_per_minute=settings.rate_limit_per_minute,
        ),
        detector=analysis.detector_status,
    )
