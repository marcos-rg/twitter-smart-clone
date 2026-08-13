"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Settings with a fixed, known configuration for assertions in tests."""
    return Settings(
        environment="test",
        cors_allowed_origins=["http://localhost:5173"],
        jwt_secret_key="test-secret",
        # Real (unmocked) readiness checks against unreachable dev hostnames
        # should fail fast in tests instead of waiting out the prod default.
        readiness_check_timeout_seconds=0.2,
    )


@pytest.fixture
def unreachable_settings() -> Settings:
    """Settings pointing at a port nothing listens on (127.0.0.1:1).

    Used by tests that exercise the "dependency unavailable" path: the
    default `postgres`/`redis`/`minio` hostnames from `test_settings` are
    unreachable when tests run on a bare host, but *are* reachable when
    tests run inside the docker-compose network (`make test`/CI), where
    Docker's embedded DNS resolves them to the real, healthy containers.
    Pointing at a closed loopback port instead keeps these tests
    deterministic in both environments.
    """
    return Settings(
        environment="test",
        cors_allowed_origins=["http://localhost:5173"],
        jwt_secret_key="test-secret",
        database_url="postgresql+asyncpg://u:p@127.0.0.1:1/db",
        redis_url="redis://127.0.0.1:1/0",
        minio_endpoint="http://127.0.0.1:1",
        readiness_check_timeout_seconds=0.2,
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    """A FastAPI app instance built from `test_settings`."""
    return create_app(test_settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A `TestClient` that runs the app's lifespan (startup/shutdown)."""
    with TestClient(app) as test_client:
        yield test_client
