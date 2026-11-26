"""FastAPI dependencies and the bounded worker pool for CPU-heavy jobs."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

import anyio.to_thread
from fastapi import Request

from api.analysis import AnalysisService
from api.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_analysis(request: Request) -> AnalysisService:
    return request.app.state.analysis


async def run_cpu_bound[ResultT](request: Request, job: Callable[..., ResultT], *args: Any, **kwargs: Any) -> ResultT:
    """Run a blocking job off the event loop, at most max_concurrent_jobs at once per process."""
    limiter: anyio.CapacityLimiter = request.app.state.cpu_limiter
    return await anyio.to_thread.run_sync(partial(job, *args, **kwargs), limiter=limiter)
