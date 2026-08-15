"""Celery task: reconcile the denormalized `tweets.like_count` /
`tweets.reply_count` counters against their source-of-truth tables
(TSC-LIKE-001).

`TweetsService.create_tweet`/`LikesService.like`/`.unlike` already keep both
counters correct transactionally (same DB transaction as the `likes`/reply
`tweets` insert, via `TweetRepository.increment_like_count`/
`increment_reply_count`'s atomic `UPDATE ... SET x = x + delta`), so under
normal operation this task finds nothing to repair. It exists as the safety
net the spec calls for (`specification.md` §5.3: "like_count and reply_count
are denormalized for read performance ... a periodic Celery task can
reconcile counters as a safety net") — covering drift from any path that
bypasses that code (a manual DB fix, a bug in an untested edge case, direct
seed-data inserts) rather than a path this codebase is expected to take
regularly.

Both counters are reconciled by the same task (rather than a like-only task)
because `app.models.tweet`'s docstring defers *both* to "a periodic Celery
reconciliation job" as one unit, and no other task in `specification/tasks.md`
ever revisits `reply_count` reconciliation.

Set-based, two `UPDATE ... FROM` statements (one per counter) rather than a
per-tweet Python loop: correcting drift across the whole table is O(1)
round-trips regardless of how many tweets exist, and `RETURNING id` gives an
exact count of rows actually repaired without a second query.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings
from app.workers.celery_app import celery_app

_RECONCILE_LIKE_COUNT_SQL = text("""
    UPDATE tweets t
    SET like_count = sub.actual_count
    FROM (
        SELECT tw.id AS tweet_id, COALESCE(lc.cnt, 0) AS actual_count
        FROM tweets tw
        LEFT JOIN (
            SELECT tweet_id, COUNT(*) AS cnt FROM likes GROUP BY tweet_id
        ) lc ON lc.tweet_id = tw.id
    ) sub
    WHERE t.id = sub.tweet_id AND t.like_count <> sub.actual_count
    RETURNING t.id
    """)

_RECONCILE_REPLY_COUNT_SQL = text("""
    UPDATE tweets t
    SET reply_count = sub.actual_count
    FROM (
        SELECT tw.id AS tweet_id, COALESCE(rc.cnt, 0) AS actual_count
        FROM tweets tw
        LEFT JOIN (
            SELECT parent_tweet_id, COUNT(*) AS cnt
            FROM tweets
            WHERE parent_tweet_id IS NOT NULL
            GROUP BY parent_tweet_id
        ) rc ON rc.parent_tweet_id = tw.id
    ) sub
    WHERE t.id = sub.tweet_id AND t.reply_count <> sub.actual_count
    RETURNING t.id
    """)


@dataclass(frozen=True)
class ReconciliationResult:
    """How many `tweets` rows had `like_count`/`reply_count` repaired."""

    like_count_repaired: int
    reply_count_repaired: int


async def _reconcile_counters(settings: Settings) -> ReconciliationResult:
    # A dedicated engine, not the API process's shared `AppResources`: this
    # runs in the `worker` container/process (mirrors
    # `app.workers.media_cleanup`'s `_cleanup_abandoned_uploads`).
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            like_result = await conn.execute(_RECONCILE_LIKE_COUNT_SQL)
            like_repaired = len(like_result.fetchall())
            reply_result = await conn.execute(_RECONCILE_REPLY_COUNT_SQL)
            reply_repaired = len(reply_result.fetchall())
        return ReconciliationResult(
            like_count_repaired=like_repaired, reply_count_repaired=reply_repaired
        )
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.reconcile_counters.reconcile_counters"
)
def reconcile_counters() -> dict[str, int]:
    """Sync Celery entry point wrapping the async reconciliation routine."""
    result = asyncio.run(_reconcile_counters(get_settings()))
    return {
        "like_count_repaired": result.like_count_repaired,
        "reply_count_repaired": result.reply_count_repaired,
    }
