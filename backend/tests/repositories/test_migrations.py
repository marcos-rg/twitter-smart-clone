"""Alembic migration round-trip + schema inspection (spec: "A clean database
upgrades to head, downgrades as documented, and upgrades again" + "Required
unique, chronological, foreign-key, partial, and trigram indexes exist").

Uses a plain async engine (not `command.*`, which is itself already
exercised as the mechanism the whole suite's `_migrated_schema` fixture
relies on) for inspection, so no extra sync (`psycopg2`) driver dependency
is needed just for tests.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from tests.repositories.conftest import TEST_DATABASE_URL, _alembic_config


async def _table_names(engine) -> set[str]:  # type: ignore[no-untyped-def]
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))


def _table_names_sync() -> set[str]:
    async def _inner() -> set[str]:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            return await _table_names(engine)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def test_migration_round_trip_base_to_head_and_back() -> None:
    """A clean database upgrades to `head`, downgrades to `base` (dropping
    every table), and upgrades to `head` again without error.

    A plain (non-`async def`) test: `alembic.command.*` drives its own
    `asyncio.run()` internally (see `alembic/env.py`), which can't be
    nested inside the event loop `pytest-asyncio` already has running for
    an `async def` test.
    """
    config = _alembic_config()

    command.downgrade(config, "base")
    assert _table_names_sync() in (set(), {"alembic_version"})

    command.upgrade(config, "head")
    assert {
        "users",
        "tweets",
        "tweet_media",
        "follows",
        "likes",
        "notifications",
        "refresh_tokens",
    } <= _table_names_sync()

    # Re-upgrading an already-head database is a no-op, not an error.
    command.upgrade(config, "head")


async def test_required_indexes_and_constraints_exist() -> None:
    """Every index/constraint the spec calls out by name in §5.1 exists
    after `upgrade head` (unique, chronological, FK, partial, trigram).
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as conn:
        index_result = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        )
        index_names = {row[0] for row in index_result}
        ext_result = await conn.execute(text("SELECT extname FROM pg_extension"))
        extensions = {row[0] for row in ext_result}
    await engine.dispose()

    assert {"citext", "pg_trgm"} <= extensions

    # Unique.
    assert "uq_users_username" in index_names
    assert "uq_users_email" in index_names
    # Trigram (fuzzy search).
    assert "ix_users_username_trgm" in index_names
    assert "ix_users_name_trgm" in index_names
    # Chronological.
    assert "ix_tweets_author_id_created_at" in index_names
    assert "ix_tweets_parent_tweet_id_created_at" in index_names
    assert "ix_tweets_created_at" in index_names
    assert "ix_notifications_recipient_id_created_at" in index_names
    # Foreign key-backed lookups.
    assert "ix_follows_follower_id" in index_names
    assert "ix_follows_followee_id" in index_names
    assert "ix_likes_tweet_id" in index_names
    # Partial (unread notifications).
    assert "ix_notifications_recipient_id_unread" in index_names
