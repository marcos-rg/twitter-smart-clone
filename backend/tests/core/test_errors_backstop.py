"""Direct unit tests for the exception-handler functions in
`app.core.errors`, covering the defensive-backstop path that is not
reachable through the normal HTTP flow (the handler is registered on the
app for exceptions Starlette hands to `ServerErrorMiddleware`, but in
practice `RequestContextMiddleware` catches unhandled exceptions first — see
that module's docstring).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.core.errors import unhandled_exception_handler


async def test_unhandled_exception_handler_returns_internal_error_envelope() -> None:
    request = MagicMock()
    request.state.request_id = "backstop-test"

    response = await unhandled_exception_handler(request, RuntimeError("boom"))

    assert response.status_code == 500
    body = bytes(response.body).decode()
    assert "internal_error" in body
    assert "boom" not in body
