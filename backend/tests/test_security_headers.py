"""Tests for the security-headers middleware (spec §10.2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_security_headers_present_on_every_response(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.headers["content-security-policy"] == (
        "default-src 'self'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"


def test_hsts_absent_when_not_production(client: TestClient) -> None:
    """HSTS must not be sent for local/test so plain-HTTP dev origins aren't broken."""
    response = client.get("/healthz")

    assert "strict-transport-security" not in response.headers


def test_hsts_present_in_production() -> None:
    prod_settings = Settings(environment="production", jwt_secret_key="prod-secret")
    app = create_app(prod_settings)

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert "strict-transport-security" in response.headers


def test_security_headers_present_on_error_responses(client: TestClient) -> None:
    """Security headers must also be applied to error responses (404 here)."""
    response = client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
