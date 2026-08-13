"""Tests for `/healthz` (liveness) and `/readyz` (readiness)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_healthz_returns_ok_without_checking_dependencies(client: TestClient) -> None:
    """Liveness must succeed even though no real Postgres/Redis/MinIO exist."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_succeeds_when_all_dependencies_are_ready(client: TestClient) -> None:
    """Readiness reports 200 once every dependency check passes."""
    with (
        patch("app.routers.health.check_database", new=AsyncMock(return_value=True)),
        patch("app.routers.health.check_redis", new=AsyncMock(return_value=True)),
        patch("app.routers.health.check_object_storage", new=AsyncMock(return_value=True)),
    ):
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok", "object_storage": "ok"},
    }


def test_readyz_fails_when_a_required_dependency_is_unavailable(client: TestClient) -> None:
    """Readiness reports 503 when any one dependency check fails."""
    with (
        patch("app.routers.health.check_database", new=AsyncMock(return_value=True)),
        patch("app.routers.health.check_redis", new=AsyncMock(return_value=False)),
        patch("app.routers.health.check_object_storage", new=AsyncMock(return_value=True)),
    ):
        response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == {"database": "ok", "redis": "unavailable", "object_storage": "ok"}


def test_readyz_fails_when_every_dependency_is_unavailable(unreachable_settings: Settings) -> None:
    """Readiness reports 503 when no dependency is reachable (e.g. cold start).

    Uses `unreachable_settings` (a closed loopback port) rather than the
    shared `client` fixture: the default `postgres`/`redis`/`minio`
    hostnames are only unreachable on a bare host, not inside the
    docker-compose network where `make test`/CI actually run this suite.
    """
    with TestClient(create_app(unreachable_settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
