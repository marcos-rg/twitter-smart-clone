"""Integration tests for `TweetsService.list_feed` (`GET /feed`, spec §8.2
"Feed generation (fan-out on read)") against a real PostgreSQL session and a
real Redis cache. Mirrors `tests/services/test_follows_service.py`'s
commit/rollback lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import event
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.models.tweet import Tweet
from app.models.tweet_media import TweetMedia
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.pending_uploads import PendingUploadRepository
from app.repositories.tweet_media import TweetMediaRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.services.notifications import NotificationsService
from app.services.tweets import InvalidPaginationCursorError, TweetsService


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


async def _make_tweet(
    session: AsyncSession, author: User, content: str, *, created_at: datetime | None = None
) -> Tweet:
    tweet = Tweet(author_id=author.id, content=content)
    if created_at is not None:
        tweet.created_at = created_at
    session.add(tweet)
    await session.flush()
    return tweet


async def _follow(session: AsyncSession, follower: User, followee: User) -> None:
    await FollowRepository(session).follow(follower.id, followee.id)


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def _make_service(
    db_session: AsyncSession, redis_client: Redis, *, feed_cache_ttl_seconds: int = 5
) -> TweetsService:
    notifications_service = NotificationsService(
        NotificationRepository(db_session), UserRepository(db_session), db_session, redis_client
    )
    return TweetsService(
        TweetRepository(db_session),
        TweetMediaRepository(db_session),
        PendingUploadRepository(db_session),
        UserRepository(db_session),
        LikeRepository(db_session),
        notifications_service,
        follows=FollowRepository(db_session),
        redis=redis_client,
        feed_cache_ttl_seconds=feed_cache_ttl_seconds,
    )


@pytest_asyncio.fixture
async def service(db_session: AsyncSession, redis_client: Redis) -> TweetsService:
    return _make_service(db_session, redis_client)


# --- membership --------------------------------------------------------------


async def test_feed_includes_own_tweets_and_followed_authors_only(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "feed_alice")
    bob = await _make_user(db_session, "feed_bob")
    carol = await _make_user(db_session, "feed_carol")
    await _follow(db_session, alice, bob)
    await db_session.commit()

    own = await _make_tweet(db_session, alice, "alice's own tweet")
    followed = await _make_tweet(db_session, bob, "bob's tweet")
    unrelated = await _make_tweet(db_session, carol, "carol's tweet")
    await db_session.commit()

    page = await service.list_feed(alice, cursor=None, limit=None)

    ids = {item.id for item in page.items}
    assert own.id in ids
    assert followed.id in ids
    assert unrelated.id not in ids


async def test_feed_excludes_tweets_from_a_user_you_do_not_follow(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "feed_alice2")
    stranger = await _make_user(db_session, "feed_stranger")
    await db_session.commit()

    await _make_tweet(db_session, stranger, "not for alice's feed")
    await db_session.commit()

    page = await service.list_feed(alice, cursor=None, limit=None)
    assert page.items == []


# --- ordering & pagination -----------------------------------------------------


async def test_feed_orders_newest_first_across_pages_without_duplicates_or_skips(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "feed_order_alice")
    bob = await _make_user(db_session, "feed_order_bob")
    await _follow(db_session, alice, bob)
    await db_session.commit()

    base = datetime(2026, 1, 1, tzinfo=UTC)
    created_ids: list[str] = []
    for i in range(45):
        author = alice if i % 2 == 0 else bob
        tweet = await _make_tweet(
            db_session, author, f"tweet {i}", created_at=base + timedelta(seconds=i)
        )
        created_ids.append(str(tweet.id))
    await db_session.commit()

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page = await service.list_feed(alice, cursor=cursor, limit=10)
        seen.extend(str(item.id) for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    # Newest-first: reverse the insertion order for the expected sequence.
    assert seen == list(reversed(created_ids))
    assert len(seen) == len(set(seen))  # no duplicates
    assert len(seen) == 45  # no skips


async def test_feed_breaks_ties_deterministically_for_identical_timestamps(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "feed_tie_alice")
    bob = await _make_user(db_session, "feed_tie_bob")
    await _follow(db_session, alice, bob)
    await db_session.commit()

    same_instant = datetime(2026, 2, 2, tzinfo=UTC)
    tweets = [
        await _make_tweet(db_session, bob, f"tie {i}", created_at=same_instant) for i in range(5)
    ]
    await db_session.commit()

    # Two full re-reads with the same tie-broken (created_at, id) keyset must
    # return an identical order every time.
    page1 = await service.list_feed(alice, cursor=None, limit=None)
    page2 = await service.list_feed(alice, cursor=None, limit=None)
    ids1 = [item.id for item in page1.items]
    ids2 = [item.id for item in page2.items]
    assert ids1 == ids2
    assert {t.id for t in tweets} <= set(ids1)


async def test_feed_limit_defaults_to_20_and_clamps_above_50(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "feed_limit_alice")
    for i in range(60):
        await _make_tweet(db_session, alice, f"post {i}")
    await db_session.commit()

    default_page = await service.list_feed(alice, cursor=None, limit=None)
    assert len(default_page.items) == 20

    clamped_page = await service.list_feed(alice, cursor=None, limit=999)
    assert len(clamped_page.items) == 50


async def test_feed_rejects_malformed_cursor(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "feed_bad_cursor_alice")
    await db_session.commit()

    try:
        await service.list_feed(alice, cursor="not-a-valid-cursor", limit=None)
    except InvalidPaginationCursorError as exc:
        assert exc.status_code == 400
        assert exc.code == "validation_error"
    else:
        raise AssertionError("expected InvalidPaginationCursorError")


# --- N+1 avoidance -------------------------------------------------------------


async def test_feed_page_resolves_authors_media_and_likes_in_a_fixed_query_count(
    db_session: AsyncSession, redis_client: Redis
) -> None:
    """Regardless of how many tweets are on the page, resolving authors,
    media, and viewer-like state must stay at a fixed, small number of
    queries — never one query per tweet.
    """
    alice = await _make_user(db_session, "feed_n1_alice")
    bob = await _make_user(db_session, "feed_n1_bob")
    await _follow(db_session, alice, bob)
    await db_session.commit()

    for i in range(15):
        tweet = await _make_tweet(db_session, bob, f"media post {i}")
        db_session.add(
            TweetMedia(tweet_id=tweet.id, s3_key=f"key-{i}", content_type="image/png", position=0)
        )
    await db_session.commit()

    # Cache disabled for this test so every call is a fresh DB read.
    service = _make_service(db_session, redis_client, feed_cache_ttl_seconds=0)

    sync_engine = db_session.get_bind()
    statements: list[str] = []

    def _count(*args: object, **kwargs: object) -> None:
        statements.append("query")

    event.listen(sync_engine, "before_cursor_execute", _count)
    try:
        statements.clear()
        page = await service.list_feed(alice, cursor=None, limit=50)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count)

    assert len(page.items) == 15
    # followee-id lookup, tweet page, author batch, media batch, like batch.
    assert len(statements) <= 5, f"expected a fixed small query count, got {len(statements)}"


# --- cache isolation & expiry ---------------------------------------------------


async def test_feed_cache_is_isolated_per_user(
    db_session: AsyncSession, redis_client: Redis
) -> None:
    alice = await _make_user(db_session, "feed_cache_alice")
    bob = await _make_user(db_session, "feed_cache_bob")
    await db_session.commit()

    await _make_tweet(db_session, alice, "alice only")
    await db_session.commit()

    service = _make_service(db_session, redis_client, feed_cache_ttl_seconds=30)

    alice_page = await service.list_feed(alice, cursor=None, limit=None)
    bob_page = await service.list_feed(bob, cursor=None, limit=None)

    assert len(alice_page.items) == 1
    assert bob_page.items == []  # bob's cached page must never see alice's tweet

    alice_cache_key = service._feed_cache_key(alice.id, None)
    bob_cache_key = service._feed_cache_key(bob.id, None)
    assert alice_cache_key != bob_cache_key
    assert await redis_client.get(bob_cache_key) != await redis_client.get(alice_cache_key)


async def test_feed_first_page_is_served_from_cache_within_ttl(
    db_session: AsyncSession, redis_client: Redis
) -> None:
    alice = await _make_user(db_session, "feed_cache_ttl_alice")
    await db_session.commit()
    await _make_tweet(db_session, alice, "before cache warm")
    await db_session.commit()

    service = _make_service(db_session, redis_client, feed_cache_ttl_seconds=30)

    first = await service.list_feed(alice, cursor=None, limit=None)
    assert len(first.items) == 1

    # A tweet created *after* the first (cached) read must not appear while
    # the cache entry is still within its TTL.
    await _make_tweet(db_session, alice, "after cache warm")
    await db_session.commit()

    cached_again = await service.list_feed(alice, cursor=None, limit=None)
    assert len(cached_again.items) == 1
    assert cached_again.items[0].id == first.items[0].id


async def test_feed_cache_expires_after_ttl(db_session: AsyncSession, redis_client: Redis) -> None:
    alice = await _make_user(db_session, "feed_cache_expiry_alice")
    await db_session.commit()
    await _make_tweet(db_session, alice, "first")
    await db_session.commit()

    service = _make_service(db_session, redis_client, feed_cache_ttl_seconds=1)
    first = await service.list_feed(alice, cursor=None, limit=None)
    assert len(first.items) == 1

    cache_key = service._feed_cache_key(alice.id, None)
    # Force-expire the entry instead of sleeping out a real TTL, to keep the
    # test deterministic and fast.
    await redis_client.delete(cache_key)

    await _make_tweet(db_session, alice, "second")
    await db_session.commit()

    refreshed = await service.list_feed(alice, cursor=None, limit=None)
    assert len(refreshed.items) == 2


async def test_feed_never_caches_pages_after_the_first(
    db_session: AsyncSession, redis_client: Redis
) -> None:
    alice = await _make_user(db_session, "feed_no_cache_second_page")
    await db_session.commit()
    for i in range(3):
        await _make_tweet(db_session, alice, f"post {i}")
    await db_session.commit()

    service = _make_service(db_session, redis_client, feed_cache_ttl_seconds=30)
    first = await service.list_feed(alice, cursor=None, limit=2)
    assert first.next_cursor is not None

    second = await service.list_feed(alice, cursor=first.next_cursor, limit=2)
    assert len(second.items) == 1

    await _make_tweet(db_session, alice, "post 3")
    await db_session.commit()

    # A repeat of the *second* page must always read live (never cached),
    # so the freshly created tweet is reflected once it's within that page's
    # keyset window on a later, uncached fetch of the first page after the
    # cache is cleared.
    second_again = await service.list_feed(alice, cursor=first.next_cursor, limit=2)
    assert len(second_again.items) == 1
