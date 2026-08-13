"""Cross-cutting ASGI middleware: request correlation IDs, access logging, and
security headers.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import internal_error_response

logger = structlog.get_logger("app.access")

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request ID and emit one structured access-log line.

    - Reuses an inbound `X-Request-ID` header when present (so upstream
      proxies/load balancers can supply a correlation id), otherwise
      generates a new UUID4.
    - Stores the id on `request.state.request_id` (read by error handlers)
      and echoes it back via the configured response header.
    - Binds `request_id`/`method`/`path` to structlog's contextvars for the
      duration of the request so every log line emitted while handling it
      carries them, then logs one summary line with `status_code` and
      `duration_ms` once the response is ready.
    - Converts an exception that escapes the router/`ExceptionMiddleware`
      into the standard error envelope itself, instead of letting it
      propagate to Starlette's `ServerErrorMiddleware`. That middleware
      always wraps the *entire* stack (it's how Starlette guarantees some
      response even if user middleware is broken), so a response built there
      would skip this middleware, CORS, and the security-headers middleware
      entirely — this middleware must be positioned inside those two (see
      `app.main.create_app`) so its envelope response still flows back out
      through them and gets the same headers as every other response.
    """

    def __init__(self, app: object, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(self._header_name) or str(uuid.uuid4())
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - converted to the standard envelope below
            logger.exception("unhandled_exception", exc_info=exc)
            response = internal_error_response(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[self._header_name] = request_id
        await logger.ainfo(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to every response (spec §10.2).

    HSTS is only sent when `enable_hsts` is true (production, behind TLS) —
    sending it over a plain-HTTP local dev origin would make browsers force
    HTTPS on subsequent requests to that host.
    """

    def __init__(self, app: object, enable_hsts: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if self._enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response
