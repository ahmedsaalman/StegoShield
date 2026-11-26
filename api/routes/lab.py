"""Evaluation Lab: live quality, robustness, attack and detector demos, plus saved results."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse

from api.analysis import AnalysisService
from api.config import Settings
from api.dependencies import get_analysis, get_settings, run_cpu_bound
from api.images import load_cover_image
from api.lab import lab_attacks, lab_detector_comparison, lab_quality, lab_results, lab_robustness
from api.lab_samples import find_sample, list_samples, run_sample
from api.schemas import (
    LabAttacksResponse,
    LabDetectorComparisonResponse,
    LabQualityResponse,
    LabResultsResponse,
    LabRobustnessResponse,
    LabSampleRunRequest,
    LabSampleRunResponse,
    LabSamplesResponse,
)

router = APIRouter(prefix="/api/lab", tags=["evaluation lab"])

LabImage = Annotated[UploadFile, File(description="Image to run the demo on (up to 1024×1024 pixels).")]


@router.get("/results", response_model=LabResultsResponse)
async def saved_results() -> LabResultsResponse:
    """Headline numbers from the held-out experiment runs (docs/results.md)."""
    return lab_results()


@router.post("/quality", response_model=LabQualityResponse)
async def quality_demo(
    request: Request, settings: Annotated[Settings, Depends(get_settings)], image: LabImage
) -> LabQualityResponse:
    """How much hiding 5–50 % test data changes the image (PSNR, SSIM)."""
    uploaded = await load_cover_image(image, settings)
    return await run_cpu_bound(request, lab_quality, uploaded.image)


@router.post("/robustness", response_model=LabRobustnessResponse)
async def robustness_demo(
    request: Request, settings: Annotated[Settings, Depends(get_settings)], image: LabImage
) -> LabRobustnessResponse:
    """Whether a hidden message survives PNG re-save, JPEG and resizing."""
    uploaded = await load_cover_image(image, settings)
    return await run_cpu_bound(request, lab_robustness, uploaded.image)


@router.post("/attacks", response_model=LabAttacksResponse)
async def attacks_demo(
    request: Request, settings: Annotated[Settings, Depends(get_settings)], image: LabImage
) -> LabAttacksResponse:
    """Wrong keys, tampering, cropping and a signature scan against a real hidden message."""
    uploaded = await load_cover_image(image, settings)
    return await run_cpu_bound(request, lab_attacks, uploaded.image)


@router.post("/detector-comparison", response_model=LabDetectorComparisonResponse)
async def detector_comparison_demo(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    analysis: Annotated[AnalysisService, Depends(get_analysis)],
    image: LabImage,
) -> LabDetectorComparisonResponse:
    """Detector score for the image clean and with LSB replacement vs matching at 5–50 %."""
    uploaded = await load_cover_image(image, settings)
    return await run_cpu_bound(request, lab_detector_comparison, uploaded.image, analysis.detector)


@router.get("/samples", response_model=LabSamplesResponse)
async def built_in_samples() -> LabSamplesResponse:
    """The built-in sample photos (held-out DIV2K crops) for the live sample run."""
    return list_samples()


@router.get("/samples/{sample_id}/image", response_class=FileResponse)
async def built_in_sample_image(sample_id: str) -> FileResponse:
    """One built-in sample photo as PNG."""
    return FileResponse(find_sample(sample_id).path, media_type="image/png")


@router.post("/samples/{sample_id}/run", response_model=LabSampleRunResponse)
async def run_built_in_sample(
    request: Request,
    analysis: Annotated[AnalysisService, Depends(get_analysis)],
    sample_id: str,
    body: LabSampleRunRequest,
) -> LabSampleRunResponse:
    """Hide a payload share in one sample with each algorithm: predicted vs actual risk, quality, changes."""
    return await run_cpu_bound(request, run_sample, sample_id, body.payload_percent, analysis.detector)
