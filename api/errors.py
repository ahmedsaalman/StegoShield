"""One JSON error shape for every failure. Messages are safe to show users and never echo input."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.capacity import CapacityExceededError
from core.crypto import AuthenticationError, InvalidPayloadError

NO_MESSAGE_FOUND_MESSAGE = (
    "Couldn't reveal a message. The password or key is wrong, the image holds no message, "
    "or the image was changed after hiding (for example, compressed, resized or edited)."
)
INTERNAL_ERROR_MESSAGE = "Something went wrong on our side. Please try again."

_HTTP_STATUS_CODES = {404: "not_found", 405: "method_not_allowed"}


class ApiError(Exception):
    """An expected failure with a stable machine code and a user-safe message."""

    def __init__(self, status_code: int, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field = field


def error_body(code: str, message: str, request_id: str | None, field: str | None = None) -> dict[str, Any]:
    """Build the JSON body shared by every error response."""
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if field is not None:
        error["field"] = field
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    """Map domain and framework exceptions to JSON error responses."""
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(AuthenticationError, _handle_no_message_found)
    app.add_exception_handler(InvalidPayloadError, _handle_no_message_found)
    app.add_exception_handler(CapacityExceededError, _handle_capacity_exceeded)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)


def _respond(request: Request, status_code: int, code: str, message: str, field: str | None = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(error_body(code, message, request_id, field), status_code=status_code)


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return _respond(request, exc.status_code, exc.code, exc.message, exc.field)


async def _handle_no_message_found(request: Request, exc: Exception) -> JSONResponse:
    # Wrong key, tampering and "no message" are deliberately indistinguishable.
    return _respond(request, 422, "no_message_found", NO_MESSAGE_FOUND_MESSAGE)


async def _handle_capacity_exceeded(request: Request, exc: Exception) -> JSONResponse:
    return _respond(request, 422, "capacity_exceeded", str(exc), field="message")


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    first_error = exc.errors()[0] if exc.errors() else {}
    field = _field_name(first_error.get("loc", ()))
    # Only the rule that failed is reported; the submitted value (maybe a password) is never echoed.
    reason = first_error.get("msg", "Invalid value")
    message = f"{field}: {reason}" if field else reason
    return _respond(request, 422, "validation_error", message, field)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    return _respond(request, exc.status_code, code, str(exc.detail))


def _field_name(location: tuple[Any, ...] | list[Any]) -> str | None:
    names = [str(part) for part in location if part not in ("body", "query", "path", "form")]
    return names[-1] if names else None
