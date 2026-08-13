"""Tests for the standard error envelope and exception handlers (spec §6.2)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


class _Body(BaseModel):
    content: str


def _app_with_test_routes(test_settings: Settings) -> FastAPI:
    """Build an app with extra routes that deliberately raise each error type."""
    app = create_app(test_settings)
    router = APIRouter()

    @router.get("/boom/http")
    async def raise_http() -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tweet not found.")

    @router.get("/boom/app-error")
    async def raise_app_error() -> None:
        raise AppError(
            "Username is already taken.",
            code="conflict",
            status_code=status.HTTP_409_CONFLICT,
            details=[{"field": "username", "issue": "already taken"}],
        )

    @router.post("/boom/validation")
    async def raise_validation(body: _Body) -> dict[str, str]:
        return {"content": body.content}

    @router.get("/boom/http-with-headers")
    async def raise_http_with_headers() -> None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests.",
            headers={"Retry-After": "30"},
        )

    @router.get("/boom/unhandled")
    async def raise_unhandled() -> None:
        raise RuntimeError("boom")

    app.include_router(router)
    return app


def _client(test_settings: Settings) -> TestClient:
    return TestClient(_app_with_test_routes(test_settings), raise_server_exceptions=False)


def test_http_exception_uses_standard_envelope(test_settings: Settings) -> None:
    with _client(test_settings) as client:
        response = client.get("/boom/http")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Tweet not found."
    assert body["error"]["request_id"] == response.headers["x-request-id"]


def test_app_error_uses_standard_envelope_with_details(test_settings: Settings) -> None:
    with _client(test_settings) as client:
        response = client.get("/boom/app-error")

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == {
        "code": "conflict",
        "message": "Username is already taken.",
        "details": [{"field": "username", "issue": "already taken"}],
        "request_id": response.headers["x-request-id"],
    }


def test_validation_error_uses_standard_envelope(test_settings: Settings) -> None:
    with _client(test_settings) as client:
        response = client.post("/boom/validation", json={"content": 123, "extra": "x"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "semantic_validation_error"
    assert body["error"]["details"]
    assert body["error"]["request_id"] == response.headers["x-request-id"]


def test_unhandled_exception_uses_standard_envelope_and_hides_details(
    test_settings: Settings,
) -> None:
    with _client(test_settings) as client:
        response = client.get("/boom/unhandled")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "boom" not in body["error"]["message"]
    assert body["error"]["request_id"] == response.headers["x-request-id"]


def test_http_exception_with_headers_are_forwarded(test_settings: Settings) -> None:
    """`HTTPException(headers=...)` (e.g. `Retry-After`) must reach the client."""
    with _client(test_settings) as client:
        response = client.get("/boom/http-with-headers")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert response.json()["error"]["code"] == "rate_limited"


def test_request_id_from_client_is_echoed_back(client: TestClient) -> None:
    """An inbound `X-Request-ID` is reused instead of generating a new one."""
    response = client.get("/healthz", headers={"X-Request-ID": "client-supplied-id"})

    assert response.headers["x-request-id"] == "client-supplied-id"
