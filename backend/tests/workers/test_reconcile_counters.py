"""Integration tests for `app.workers.reconcile_counters` (TSC-LIKE-001)
against real PostgreSQL: deliberately drift `tweets.like_count`/
`reply_count` away from the source-of-truth `likes`/`tweets` rows, then
confirm the task repairs exactly the drifted rows and leaves correct rows
untouched.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic import command
from app.core.config import Settings
from app.models.like import Like
from app.models.tweet import Tweet
from app.models.user import User
from app.workers.reconcile_counters import _reconcile_counters, reconcile_counters
from tests.repositories.conftest import _alembic_config

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://twitter_smart_clone:twitter_smart_clone_dev"
        "@localhost:5432/twitter_smart_clone",
    ),
)


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_reconcile() -> None:
    command.upgrade(_alembic_config(), "head")


@pytest.fixture
def reconcile_settings() -> Settings:
    return Settings(environment="test", database_url=TEST_DATABASE_URL)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, "
                "tweet_media, tweets, users CASCADE"
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


async def _make_user(session: AsyncSession, username: str) -> User:
    user = User(
        name=username.title(),
        username=username,
        email=f"{username}@example.com",
        password_hash="hash",
    )
    session.add(user)
    await session.flush()
    return user


async def test_reconcile_repairs_drifted_like_and_reply_counts(
    reconcile_settings: Settings, db_session: AsyncSession
) -> None:
    author = await _make_user(db_session, "reconcile_author")
    liker_a = await _make_user(db_session, "reconcile_liker_a")
    liker_b = await _make_user(db_session, "reconcile_liker_b")

    root = Tweet(author_id=author.id, content="root tweet", like_count=0, reply_count=0)
    db_session.add(root)
    await db_session.flush()

    # Two real likes, but the denormalized counter is deliberately wrong (drifted high).
    db_session.add(Like(user_id=liker_a.id, tweet_id=root.id))
    db_session.add(Like(user_id=liker_b.id, tweet_id=root.id))
    root.like_count = 99  # drift: should be 2
    db_session.add(root)

    # One real reply, but reply_count is deliberately wrong (drifted low, at 0).
    reply = Tweet(author_id=liker_a.id, content="a reply", parent_tweet_id=root.id)
    db_session.add(reply)

    # A second tweet whose counters are already correct (0 likes, 0 replies)
    # and must be left untouched.
    untouched = Tweet(author_id=author.id, content="untouched tweet", like_count=0, reply_count=0)
    db_session.add(untouched)

    # A third tweet with a stale nonzero like_count but zero actual likes
    # (drift down to 0), to prove the LEFT JOIN branch (no matching likes
    # row at all) is also repaired.
    drifted_to_zero = Tweet(
        author_id=author.id, content="drifted to zero", like_count=7, reply_count=0
    )
    db_session.add(drifted_to_zero)

    await db_session.commit()

    result = await _reconcile_counters(reconcile_settings)
    # root: like_count drifted (99 -> 2) and reply_count drifted (0 -> 1).
    # drifted_to_zero: like_count drifted (7 -> 0).
    assert result.like_count_repaired == 2
    assert result.reply_count_repaired == 1

    engine = create_async_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as fresh_session:
        refreshed_root = await fresh_session.get(Tweet, root.id)
        assert refreshed_root is not None
        assert refreshed_root.like_count == 2
        assert refreshed_root.reply_count == 1

        refreshed_untouched = await fresh_session.get(Tweet, untouched.id)
        assert refreshed_untouched is not None
        assert refreshed_untouched.like_count == 0
        assert refreshed_untouched.reply_count == 0

        refreshed_drifted = await fresh_session.get(Tweet, drifted_to_zero.id)
        assert refreshed_drifted is not None
        assert refreshed_drifted.like_count == 0
    await engine.dispose()

    # Running again is a no-op: everything is already correct.
    second_run = await _reconcile_counters(reconcile_settings)
    assert second_run.like_count_repaired == 0
    assert second_run.reply_count_repaired == 0


def test_celery_task_entry_point_runs_synchronously() -> None:
    """The registered Celery task (the sync `asyncio.run(...)` wrapper
    around `_reconcile_counters`) is what `celery ... call
    app.workers.reconcile_counters.reconcile_counters` (or, once wired, a
    `beat` schedule) actually invokes.
    """
    result = reconcile_counters.run()
    assert set(result.keys()) == {"like_count_repaired", "reply_count_repaired"}
    assert result["like_count_repaired"] >= 0
    assert result["reply_count_repaired"] >= 0
