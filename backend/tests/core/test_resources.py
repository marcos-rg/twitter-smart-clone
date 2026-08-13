"""Tests for async resource lifecycle and readiness checks
(`app.core.resources`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.resources import (
    AppResources,
    build_resources,
    check_database,
    check_object_storage,
    check_redis,
)


@pytest.fixture
async def resources(test_settings: Settings) -> AsyncIterator[AppResources]:
    """Real (but unconnected) resources: connections are lazy, so this never
    touches a network even without Postgres/Redis/MinIO running.
    """
    built = await build_resources(test_settings)
    try:
        yield built
    finally:
        await built.aclose()


@pytest.fixture
async def unreachable_resources(unreachable_settings: Settings) -> AsyncIterator[AppResources]:
    """Resources configured against a guaranteed-closed port, for
    deterministic "dependency unavailable" tests (see
    `unreachable_settings`'s docstring for why `resources`/`test_settings`
    aren't sufficient here).
    """
    built = await build_resources(unreachable_settings)
    try:
        yield built
    finally:
        await built.aclose()


async def test_build_resources_does_not_require_reachable_dependencies(
    resources: AppResources,
) -> None:
    """Startup succeeds even when no dependency is actually reachable yet."""
    assert resources.db_engine is not None
    assert resources.redis is not None
    assert resources.s3_client is not None


async def test_aclose_disposes_every_resource(test_settings: Settings) -> None:
    """Shutdown must release every acquired resource exactly once."""
    built = await build_resources(test_settings)

    # `AsyncEngine`/`Redis` expose `dispose`/`aclose` as read-only descriptors
    # on the class, so instance-level monkeypatching isn't possible; patch
    # the class attribute for the duration of this test instead.
    with (
        patch.object(AsyncEngine, "dispose", new=AsyncMock()) as mock_dispose,
        patch.object(type(built.redis), "aclose", new=AsyncMock()) as mock_redis_aclose,
    ):
        await built.aclose()

        mock_dispose.assert_awaited_once()
        mock_redis_aclose.assert_awaited_once()


async def test_check_database_returns_false_when_unreachable(
    unreachable_resources: AppResources,
) -> None:
    assert await check_database(unreachable_resources, timeout=0.2) is False


async def test_check_redis_returns_false_when_unreachable(
    unreachable_resources: AppResources,
) -> None:
    assert await check_redis(unreachable_resources, timeout=0.2) is False


async def test_check_object_storage_returns_false_when_unreachable(
    unreachable_resources: AppResources,
) -> None:
    assert await check_object_storage(unreachable_resources, timeout=0.2) is False


async def test_check_database_returns_true_when_query_succeeds(
    resources: AppResources,
) -> None:
    conn_cm = AsyncMock()
    conn_cm.__aenter__.return_value = AsyncMock(execute=AsyncMock())

    with patch.object(AsyncEngine, "connect", new=MagicMock(return_value=conn_cm)):
        assert await check_database(resources, timeout=0.2) is True


async def test_check_redis_returns_true_when_ping_succeeds(resources: AppResources) -> None:
    resources.redis.ping = AsyncMock(return_value=True)  # type: ignore[method-assign]

    assert await check_redis(resources, timeout=0.2) is True


async def test_check_object_storage_returns_true_when_head_bucket_succeeds(
    resources: AppResources,
) -> None:
    resources.s3_client.head_bucket = AsyncMock(return_value={})

    assert await check_object_storage(resources, timeout=0.2) is True
