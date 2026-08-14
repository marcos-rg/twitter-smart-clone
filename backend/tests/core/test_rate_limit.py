"""Tests for the Redis-backed sliding-window rate limiter
(`app.core.rate_limit`, spec §10.3).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.rate_limit import RateLimitExceeded, check_rate_limit


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def _unique_key() -> str:
    return f"test:{uuid.uuid4()}"


async def test_allows_requests_under_the_limit(redis_client: Redis) -> None:
    key = _unique_key()
    for _ in range(3):
        await check_rate_limit(redis_client, key=key, limit=3, window_seconds=60)


async def test_rejects_requests_once_the_limit_is_reached(redis_client: Redis) -> None:
    key = _unique_key()
    for _ in range(3):
        await check_rate_limit(redis_client, key=key, limit=3, window_seconds=60)

    with pytest.raises(RateLimitExceeded) as exc_info:
        await check_rate_limit(redis_client, key=key, limit=3, window_seconds=60)
    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retry_after_seconds > 0
    assert exc_info.value.headers == {"Retry-After": str(exc_info.value.retry_after_seconds)}


async def test_different_keys_have_independent_limits(redis_client: Redis) -> None:
    key_a, key_b = _unique_key(), _unique_key()
    await check_rate_limit(redis_client, key=key_a, limit=1, window_seconds=60)
    with pytest.raises(RateLimitExceeded):
        await check_rate_limit(redis_client, key=key_a, limit=1, window_seconds=60)

    # A different key is unaffected by key_a's exhausted limit.
    await check_rate_limit(redis_client, key=key_b, limit=1, window_seconds=60)


async def test_window_expiry_allows_requests_again(redis_client: Redis) -> None:
    key = _unique_key()
    await check_rate_limit(redis_client, key=key, limit=1, window_seconds=1)
    with pytest.raises(RateLimitExceeded):
        await check_rate_limit(redis_client, key=key, limit=1, window_seconds=1)

    import asyncio

    await asyncio.sleep(1.2)
    # The 1-second window has elapsed, so this request is allowed again.
    await check_rate_limit(redis_client, key=key, limit=1, window_seconds=1)
