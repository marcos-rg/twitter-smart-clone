"""App-factory-level smoke tests: metadata, versioned docs/OpenAPI routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_app_metadata(client: TestClient) -> None:
    """The app factory should apply the configured title/version."""
    assert client.app.title == "Twitter Smart Clone API"  # type: ignore[attr-defined]
    assert client.app.version == "0.1.0"  # type: ignore[attr-defined]


def test_openapi_json_is_generated_under_v1(client: TestClient) -> None:
    """OpenAPI schema is served at the versioned path (spec §6)."""
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Twitter Smart Clone API"
    assert "/healthz" in schema["paths"]
    assert "/readyz" in schema["paths"]


def test_docs_ui_is_served_under_v1(client: TestClient) -> None:
    """Swagger UI is served at `/api/v1/docs` (spec §6)."""
    response = client.get("/api/v1/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
