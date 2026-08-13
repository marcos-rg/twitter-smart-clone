"""RFC-9457-inspired error envelope and exception handlers (spec §6.2).

Every error response body has the shape:

    {"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}

`code` is a stable machine-readable string, `message` is user-safe (never a
raw exception message for unhandled 500s), `details` is an optional list of
field-level issues, and `request_id` echoes the same id as the
`X-Request-ID` response header/log lines so a report can be correlated.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger("app.errors")

# Default machine-readable `code` per HTTP status, matching specification.md §6.2.
_STATUS_CODE_DEFAULTS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "validation_error",
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "semantic_validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}

_GENERIC_MESSAGE_FOR_STATUS: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: "Authentication is required to access this resource.",
    status.HTTP_403_FORBIDDEN: "You do not have permission to perform this action.",
    status.HTTP_404_NOT_FOUND: "The requested resource was not found.",
    status.HTTP_409_CONFLICT: "The request could not be completed due to a conflict.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests. Please try again later.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "An unexpected error occurred.",
}


class AppError(Exception):
    """Base class for domain errors that should render as the standard envelope.

    Feature code (services/routers in later tasks) raises subclasses of this
    instead of a bare `HTTPException` so the machine-readable `code` is
    explicit rather than derived from the HTTP status alone.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "validation_error"

    def __init__(
        self,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": _request_id(request),
        }
    }
    return JSONResponse(status_code=status_code, content=body)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle domain errors raised as `AppError` subclasses."""
    assert isinstance(exc, AppError)
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle `HTTPException`s raised anywhere in the stack (incl. FastAPI's)."""
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODE_DEFAULTS.get(exc.status_code, "http_error")
    detail = exc.detail
    message = (
        detail
        if isinstance(detail, str) and detail
        else _GENERIC_MESSAGE_FOR_STATUS.get(exc.status_code, "An error occurred.")
    )
    response = _error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
    )
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI/Pydantic request validation failures (422)."""
    assert isinstance(exc, RequestValidationError)
    details = [
        {
            "field": ".".join(str(loc) for loc in error["loc"] if loc != "body"),
            "issue": error["msg"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=_STATUS_CODE_DEFAULTS[status.HTTP_422_UNPROCESSABLE_CONTENT],
        message="The request could not be validated.",
        details=details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any exception not otherwise caught: log the traceback, hide details."""
    await logger.aexception("unhandled_exception", exc_info=exc)
    return internal_error_response(request)


def internal_error_response(request: Request) -> JSONResponse:
    """Build the standard 500 envelope. Shared by `unhandled_exception_handler`
    (registered for exceptions Starlette hands to `ServerErrorMiddleware`) and
    `RequestContextMiddleware` (which catches exceptions itself so the
    response still flows back through CORS/security-header middleware — see
    that module's docstring for why).
    """
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=_STATUS_CODE_DEFAULTS[status.HTTP_500_INTERNAL_SERVER_ERROR],
        message=_GENERIC_MESSAGE_FOR_STATUS[status.HTTP_500_INTERNAL_SERVER_ERROR],
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every error handler onto the FastAPI app instance."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
