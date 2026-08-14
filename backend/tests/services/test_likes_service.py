"""Integration tests for `LikesService` against a real PostgreSQL session
and a real Redis pub/sub channel (spec §5.1, §6.1). Mirrors
`tests/services/test_follows_service.py`'s commit/rollback lifecycle: drives
`session.commit()`/`run_post_commit_callbacks` manually, exactly what
`get_db_session` (`app.core.deps`) does for a real request.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.outbox import run_post_commit_callbacks
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.services.likes import LikesService, TweetNotFoundError
from app.services.notifications import NotificationsService
from tests.repositories.conftest import TEST_DATABASE_URL


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


async def _make_tweet(session: AsyncSession, author: User, content: str) -> Tweet:
    tweet = Tweet(author_id=author.id, content=content)
    session.add(tweet)
    await session.flush()
    return tweet


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def service(db_session: AsyncSession, redis_client: Redis) -> LikesService:
    notifications_service = NotificationsService(
        NotificationRepository(db_session), UserRepository(db_session), db_session, redis_client
    )
    return LikesService(
        LikeRepository(db_session), TweetRepository(db_session), notifications_service
    )


async def test_like_creates_exactly_one_notification_after_commit(
    db_session: AsyncSession, service: LikesService
) -> None:
    alice = await _make_user(db_session, "likes_svc_alice")
    bob = await _make_user(db_session, "likes_svc_bob")
    tweet = await _make_tweet(db_session, bob, "hello")

    result = await service.like(alice, tweet.id)
    assert result.liked is True
    assert result.like_count == 1

    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(bob.id, cursor=None, limit=10)
    assert len(page.items) == 1
    assert page.items[0].actor_id == alice.id
    assert page.items[0].type == "like"
    assert page.items[0].tweet_id == tweet.id


async def test_repeat_like_is_idempotent_and_creates_no_second_notification(
    db_session: AsyncSession, service: LikesService
) -> None:
    alice = await _make_user(db_session, "likes_svc_repeat_alice")
    bob = await _make_user(db_session, "likes_svc_repeat_bob")
    tweet = await _make_tweet(db_session, bob, "hello again")

    await service.like(alice, tweet.id)
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    result = await service.like(alice, tweet.id)
    assert result.liked is True
    assert result.like_count == 1
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(bob.id, cursor=None, limit=10)
    assert len(page.items) == 1

    # `increment_like_count` updates `tweets.like_count` via a Core-level
    # `UPDATE`, which bypasses this session's ORM identity map — without an
    # explicit `refresh()`, re-fetching `tweet` here would just return the
    # already-loaded (stale) Python object instead of hitting the database.
    await db_session.refresh(tweet)
    tweets = TweetRepository(db_session)
    refreshed = await tweets.get(tweet.id)
    assert refreshed is not None
    assert refreshed.like_count == 1


async def test_unlike_is_idempotent_and_never_notifies(
    db_session: AsyncSession, service: LikesService
) -> None:
    alice = await _make_user(db_session, "likes_svc_unlike_alice")
    bob = await _make_user(db_session, "likes_svc_unlike_bob")
    tweet = await _make_tweet(db_session, bob, "unlike me")

    await service.like(alice, tweet.id)
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    result = await service.unlike(alice, tweet.id)
    assert result.liked is False
    assert result.like_count == 0

    # Unliking again is a no-op, not an error.
    result_again = await service.unlike(alice, tweet.id)
    assert result_again.liked is False
    assert result_again.like_count == 0
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(bob.id, cursor=None, limit=10)
    assert len(page.items) == 1  # only the original like notification, none for unlike

    await db_session.refresh(tweet)  # see the identity-map note in the repeat-like test above
    tweets = TweetRepository(db_session)
    refreshed = await tweets.get(tweet.id)
    assert refreshed is not None
    assert refreshed.like_count == 0


async def test_self_like_notifies_no_one(db_session: AsyncSession, service: LikesService) -> None:
    alice = await _make_user(db_session, "likes_svc_self_alice")
    tweet = await _make_tweet(db_session, alice, "my own tweet")

    result = await service.like(alice, tweet.id)
    assert result.liked is True
    assert result.like_count == 1
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(alice.id, cursor=None, limit=10)
    assert page.items == []


async def test_like_unknown_tweet_raises_not_found(
    db_session: AsyncSession, service: LikesService
) -> None:
    alice = await _make_user(db_session, "likes_svc_notfound_alice")

    try:
        await service.like(alice, uuid.uuid4())
        raise AssertionError("expected TweetNotFoundError")
    except TweetNotFoundError:
        pass


async def test_concurrent_duplicate_like_calls_leave_one_row_and_correct_count(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    """Each concurrent call gets its own request-scoped session (mirroring a
    real request), a genuine race for the same `(user_id, tweet_id)` pair --
    not merely a sequential repeat call within one session.
    """
    alice = await _make_user(db_session, "likes_svc_race_alice")
    bob = await _make_user(db_session, "likes_svc_race_bob")
    tweet = await _make_tweet(db_session, bob, "race target")
    await db_session.commit()

    engine = create_async_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _like_once() -> None:
        async with sessionmaker() as session:
            redis_client = Redis.from_url(test_settings.redis_url, decode_responses=True)
            try:
                notifications_service = NotificationsService(
                    NotificationRepository(session), UserRepository(session), session, redis_client
                )
                svc = LikesService(
                    LikeRepository(session), TweetRepository(session), notifications_service
                )
                await svc.like(alice, tweet.id)
                await session.commit()
                await run_post_commit_callbacks(session)
            finally:
                await redis_client.aclose()

    try:
        await asyncio.gather(*(_like_once() for _ in range(5)))
    finally:
        await engine.dispose()

    async with engine.connect() as conn:
        like_rows = (
            await conn.execute(
                text("SELECT COUNT(*) FROM likes WHERE user_id = :u AND tweet_id = :t"),
                {"u": str(alice.id), "t": str(tweet.id)},
            )
        ).scalar_one()
        like_count = (
            await conn.execute(
                text("SELECT like_count FROM tweets WHERE id = :t"), {"t": str(tweet.id)}
            )
        ).scalar_one()
        notif_count = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM notifications WHERE recipient_id = :r AND type = 'like'"
                ),
                {"r": str(bob.id)},
            )
        ).scalar_one()
    await engine.dispose()

    assert like_rows == 1
    assert like_count == 1
    assert notif_count == 1
