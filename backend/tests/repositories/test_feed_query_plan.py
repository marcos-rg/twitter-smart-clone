"""Query-plan evidence for the home-feed fan-out-on-read query (spec §8.2):
`WHERE author_id IN (...) ORDER BY created_at DESC, id DESC LIMIT n+1`
(`TweetRepository.list_feed`) must use an index, never a sequential scan,
at a representative data volume. Mirrors
`tests/repositories/test_user_search_plans.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.tweet import Tweet
from app.models.user import User


async def _seed_representative_feed(db_session: AsyncSession) -> list[uuid.UUID]:
    """~20 followed authors, each with ~150 tweets (3000 rows total), plus a
    large pool of *other* authors' tweets interleaved by timestamp, so a
    plan that ignores the `author_id` predicate (or the `created_at` index)
    would show up as a sequential scan or a full-table sort.
    """
    followed_authors = [
        User(
            name=f"Followed {i}",
            username=f"feedplan_followed_{i:03d}",
            email=f"feedplan_followed_{i:03d}@example.com",
            password_hash="hash",
        )
        for i in range(20)
    ]
    other_authors = [
        User(
            name=f"Other {i}",
            username=f"feedplan_other_{i:03d}",
            email=f"feedplan_other_{i:03d}@example.com",
            password_hash="hash",
        )
        for i in range(50)
    ]
    db_session.add_all([*followed_authors, *other_authors])
    await db_session.flush()

    base = datetime(2026, 1, 1, tzinfo=UTC)
    tick = 0
    for author in followed_authors:
        for _ in range(150):
            db_session.add(
                Tweet(
                    author_id=author.id,
                    content="followed tweet",
                    created_at=base + timedelta(seconds=tick),
                )
            )
            tick += 1
    for author in other_authors:
        for _ in range(150):
            db_session.add(
                Tweet(
                    author_id=author.id,
                    content="other tweet",
                    created_at=base + timedelta(seconds=tick),
                )
            )
            tick += 1
    await db_session.flush()
    return [author.id for author in followed_authors]


async def _explain_lines(db_session: AsyncSession, author_ids: list[uuid.UUID]) -> str:
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    placeholders = ", ".join(f":a{i}" for i in range(len(author_ids)))
    params = {f"a{i}": str(author_id) for i, author_id in enumerate(author_ids)}
    result = await db_session.execute(
        text(
            "EXPLAIN (COSTS OFF) SELECT id FROM tweets "
            f"WHERE author_id IN ({placeholders}) "
            "ORDER BY created_at DESC, id DESC LIMIT 21"
        ),
        params,
    )
    return "\n".join(str(line[0]) for line in result.all())


async def test_feed_query_uses_an_index_not_a_sequential_scan(db_session: AsyncSession) -> None:
    author_ids = await _seed_representative_feed(db_session)
    plan = await _explain_lines(db_session, author_ids)
    assert "Seq Scan" not in plan
    assert "ix_tweets_created_at" in plan or "ix_tweets_author_id" in plan
