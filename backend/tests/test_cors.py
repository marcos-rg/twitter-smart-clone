"""Tests for environment-driven CORS configuration (spec §10.4 / acceptance
criteria: allowed origins succeed with credentials, unlisted origins are
rejected).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_allowed_origin_receives_cors_headers_with_credentials(client: TestClient) -> None:
    """A request from the configured SPA origin gets `Access-Control-Allow-*`."""
    response = client.get("/healthz", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unlisted_origin_does_not_receive_cors_headers(client: TestClient) -> None:
    """A request from an origin not in `cors_allowed_origins` is not granted CORS."""
    response = client.get("/healthz", headers={"Origin": "http://evil.example.com"})

    # The request itself still reaches the app (CORS is enforced by the
    # browser, not the server), but no permissive header is echoed back for
    # this origin, so the browser will block the response from JS callers.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_allowed_origin_succeeds(client: TestClient) -> None:
    """An `OPTIONS` preflight from the allowed origin is granted."""
    response = client.options(
        "/healthz",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_for_unlisted_origin_is_rejected(client: TestClient) -> None:
    """An `OPTIONS` preflight from an unlisted origin is rejected."""
    response = client.options(
        "/healthz",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
