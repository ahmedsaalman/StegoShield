"""Application factory. Run with: uvicorn api.main:app"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from api import __version__
from api.analysis import AnalysisService
from api.config import Settings
from api.errors import register_error_handlers
from api.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from api.routes import analysis, keys, lab, meta, stego

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
HASHED_ASSET_CACHE = "public, max-age=31536000, immutable"
HTML_CACHE = "no-cache"


def create_app(settings: Settings | None = None, analysis_service: AnalysisService | None = None) -> FastAPI:
    """Build the API (and, when a front-end build exists, serve it from the same origin)."""
    settings = settings or Settings.from_env()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="StegoShield API",
        version=__version__,
        description="Encrypted steganography and steganalysis. Stateless: nothing you upload is stored.",
        docs_url="/api/docs" if settings.enable_docs else None,
        openapi_url="/api/openapi.json" if settings.enable_docs else None,
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.analysis = analysis_service or AnalysisService.load(settings.detector_path)

    register_error_handlers(app)
    for router in (meta.router, keys.router, stego.router, analysis.router, lab.router):
        app.include_router(router)
    _add_middleware(app, settings)
    _mount_front_end(app, settings.static_dir)
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.cpu_limiter = anyio.CapacityLimiter(app.state.settings.max_concurrent_jobs)
    yield


def _add_middleware(app: FastAPI, settings: Settings) -> None:
    # Starlette runs the last-added middleware first, so this list is innermost → outermost.
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_request_bytes)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            expose_headers=["Content-Disposition", "X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.enable_hsts)


def _mount_front_end(app: FastAPI, static_dir: Path | None) -> None:
    if static_dir is None or not (static_dir / "index.html").is_file():
        return
    app.mount("/", SinglePageApp(directory=static_dir), name="front-end")


class SinglePageApp(StaticFiles):
    """Serves the built React app, sending index.html for client-side routes like /hide."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(404, "No such API endpoint.")
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = await super().get_response("index.html", scope)
        is_hashed_asset = path.startswith("assets/") and response.status_code == 200
        response.headers["Cache-Control"] = HASHED_ASSET_CACHE if is_hashed_asset else HTML_CACHE
        return response


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format=LOG_FORMAT)
    logging.getLogger("stegoshield").setLevel(level)


app = create_app()
