"""Redis-backed sliding-window rate limiting (spec §10.3).

A minimal, dependency-free (beyond `redis`) sliding-window limiter built on a
Redis sorted set per `key`: each request adds a member scored by its
timestamp, expired members (older than the window) are trimmed, and the
remaining cardinality is the request count within the window. This is more
accurate than a fixed-window counter (no burst-at-the-boundary problem) while
still being O(log n) per request.

`TSC-AUTH-001` is the first consumer (`/auth/register`, `/auth/login`,
`/auth/refresh` at 10/min/IP per spec §10.3's suggested default); later
feature tasks reuse `check_rate_limit` for their own per-user limits.
"""

from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis

from app.core.errors import AppError


class RateLimitExceeded(AppError):
    """Raised when a caller has exceeded its allotted requests in the window.

    Carries `retry_after_seconds` so the router can attach a `Retry-After`
    header (spec §6.2: "`429` rate limited (includes `Retry-After`)").
    """

    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after_seconds)},
        )
        self.retry_after_seconds = retry_after_seconds


async def check_rate_limit(
    redis: Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Raise `RateLimitExceeded` if `key` has made >= `limit` requests in the
    trailing `window_seconds`; otherwise record this request and return.
    """
now = time.time()
window_start = now - window_seconds
redis_key = f"ratelimit:{key}"
member = f"{now}:{uuid.uuid4()}"

async with redis.pipeline(transaction=True) as pipe:
    pipe.zremrangebyscore(redis_key, 0, window_start)
    pipe.zadd(redis_key, {member: now})
    pipe.zcard(redis_key)
    pipe.expire(redis_key, window_seconds)
    results = await pipe.execute()
current_count = int(results[2])

if current_count > limit:
    # Remove this request's marker so we don't permanently exceed the limit.
    await redis.zrem(redis_key, member)
    oldest = await redis.zrange(redis_key, 0, 0, withscores=True)
    retry_after = window_seconds
    if oldest:
        oldest_score = float(oldest[0][1])
        retry_after = max(1, int(oldest_score + window_seconds - now))
    raise RateLimitExceeded(retry_after)
