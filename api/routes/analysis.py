"""Capacity, pre-flight risk check and steganalysis detection."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from api.analysis import AnalysisService, describe_capacity
from api.config import Settings
from api.dependencies import get_analysis, get_settings, run_cpu_bound
from api.images import load_cover_image
from api.schemas import CapacityResponse, DetectionResponse, KeyMethod, PreflightResponse

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/capacity", response_model=CapacityResponse)
async def measure_capacity(
    settings: Annotated[Settings, Depends(get_settings)],
    image: Annotated[UploadFile, File(description="Candidate cover image.")],
) -> CapacityResponse:
    """Largest message the image can carry, per protection method."""
    uploaded = await load_cover_image(image, settings)
    return describe_capacity(uploaded.image, uploaded.is_lossy)


@router.post("/preflight", response_model=PreflightResponse)
async def check_preflight(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    analysis: Annotated[AnalysisService, Depends(get_analysis)],
    image: Annotated[UploadFile, File(description="Candidate cover image.")],
    message_bytes: Annotated[int, Form(ge=0, le=100_000_000)],
    method: Annotated[KeyMethod, Form()] = KeyMethod.PASSWORD,
) -> PreflightResponse:
    """Estimate how detectable a message of this size would be in this image, before hiding it."""
    uploaded = await load_cover_image(image, settings)
    return await run_cpu_bound(request, analysis.preflight, uploaded.image, message_bytes, method, uploaded.is_lossy)


@router.post("/detect", response_model=DetectionResponse)
async def detect_hidden_data(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    analysis: Annotated[AnalysisService, Depends(get_analysis)],
    image: Annotated[UploadFile, File(description="Image to scan for hidden data.")],
) -> DetectionResponse:
    """Probability that the image contains hidden data, with the indicators behind it."""
    uploaded = await load_cover_image(image, settings)
    return await run_cpu_bound(request, analysis.detect, uploaded.image)
