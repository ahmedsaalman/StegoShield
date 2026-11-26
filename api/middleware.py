"""ASGI middleware: request IDs and logging, crash containment, security headers, rate and size limits."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import INTERNAL_ERROR_MESSAGE, error_body

logger = logging.getLogger("stegoshield.api")

RATE_LIMIT_WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 10_000
DOCS_PATHS = ("/api/docs", "/api/openapi.json")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HSTS_HEADER_VALUE = "max-age=31536000; includeSubDomains"


class RequestContextMiddleware:
    """Tags each request with an ID, logs one line per request, and turns crashes into a safe 500.

    Only method, path, status and timing are logged: never bodies, which hold images, messages and keys.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = time.perf_counter()
        response_state = {"status": 500, "started": False}

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_state.update(status=message["status"], started=True)
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception("Unhandled error request_id=%s", request_id)
            if response_state["started"]:
                raise
            response = JSONResponse(error_body("internal_error", INTERNAL_ERROR_MESSAGE, request_id), status_code=500)
            await response(scope, receive, send_with_request_id)
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "%s %s %s %.0fms request_id=%s",
                scope["method"],
                scope["path"],
                response_state["status"],
                elapsed_ms,
                request_id,
            )


class SecurityHeadersMiddleware:
    """Adds browser security headers to every response and stops caching of API responses."""

    def __init__(self, app: ASGIApp, enable_hsts: bool) -> None:
        self.app = app
        self.enable_hsts = enable_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._apply(MutableHeaders(scope=message), path)
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _apply(self, headers: MutableHeaders, path: str) -> None:
        for name, value in BASE_SECURITY_HEADERS.items():
            headers.setdefault(name, value)
        if not path.startswith(DOCS_PATHS):
            # Swagger UI loads its assets from a CDN, so the docs page gets no CSP.
            headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if path.startswith("/api/"):
            # Responses can carry decrypted messages and private keys.
            headers["Cache-Control"] = "no-store"
        if self.enable_hsts:
            headers.setdefault("Strict-Transport-Security", HSTS_HEADER_VALUE)


class RateLimitMiddleware:
    """Sliding-window limit on POST /api/* per client IP.

    Every POST does CPU-heavy work (PBKDF2, embedding, feature extraction), so this is the main
    protection against one client starving the others. State is per process.
    """

    def __init__(self, app: ASGIApp, requests_per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.requests_per_minute = requests_per_minute
        self.clock = clock
        self._history: dict[str, deque[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_limited_request(scope):
            await self.app(scope, receive, send)
            return
        retry_after = self._record_and_get_retry_after(_client_key(scope))
        if retry_after == 0:
            await self.app(scope, receive, send)
            return
        request_id = scope.get("state", {}).get("request_id")
        message = f"Too many requests. Please wait {retry_after} seconds and try again."
        response = JSONResponse(
            error_body("rate_limited", message, request_id),
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)

    def _is_limited_request(self, scope: Scope) -> bool:
        return (
            self.requests_per_minute > 0
            and scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].startswith("/api/")
        )

    def _record_and_get_retry_after(self, client_key: str) -> int:
        """Record this request if allowed. Returns 0 when allowed, else whole seconds to wait."""
        now = self.clock()
        timestamps = self._history.setdefault(client_key, deque())
        while timestamps and now - timestamps[0] >= RATE_LIMIT_WINDOW_SECONDS:
            timestamps.popleft()
        if len(timestamps) >= self.requests_per_minute:
            return max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - timestamps[0])) + 1)
        timestamps.append(now)
        self._forget_idle_clients(now)
        return 0

    def _forget_idle_clients(self, now: float) -> None:
        if len(self._history) <= MAX_TRACKED_CLIENTS:
            return
        idle = [key for key, stamps in self._history.items() if not stamps or now - stamps[-1] >= 60]
        for key in idle:
            del self._history[key]


class BodySizeLimitMiddleware:
    """Rejects request bodies above a byte ceiling, whether or not Content-Length is declared."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self._declared_length(scope) > self.max_body_bytes:
            await self._reject(scope, receive, send)
            return

        received_bytes = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    def _declared_length(self, scope: Scope) -> int:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return 0
        return 0

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit_mb = self.max_body_bytes / (1024 * 1024)
        request_id = scope.get("state", {}).get("request_id")
        message = f"The upload is too large. The limit is about {limit_mb:.0f} MB per request."
        response = JSONResponse(error_body("request_too_large", message, request_id), status_code=413)
        await response(scope, receive, send)


class _BodyTooLargeError(Exception):
    pass


def _client_key(scope: Scope) -> str:
    client = scope.get("client")
    return client[0] if client else "unknown"
