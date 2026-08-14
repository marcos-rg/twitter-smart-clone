"""Integration tests for `FollowsService` against a real PostgreSQL session
and a real Redis pub/sub channel (spec §5.1, §6.1). Mirrors
`tests/services/test_notifications_service.py`'s commit/rollback lifecycle:
drives `session.commit()`/`run_post_commit_callbacks` manually, exactly what
`get_db_session` (`app.core.deps`) does for a real request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.outbox import run_post_commit_callbacks
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRepository
from app.services.follows import CannotFollowSelfError, FollowsService, UserNotFoundError
from app.services.notifications import NotificationsService


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


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def service(db_session: AsyncSession, redis_client: Redis) -> FollowsService:
    notifications_service = NotificationsService(
        NotificationRepository(db_session), UserRepository(db_session), db_session, redis_client
    )
    return FollowsService(FollowRepository(db_session), UserRepository(db_session), notifications_service)


async def test_follow_creates_exactly_one_notification_after_commit(
    db_session: AsyncSession, service: FollowsService
) -> None:
    alice = await _make_user(db_session, "follows_svc_alice")
    bob = await _make_user(db_session, "follows_svc_bob")

    result = await service.follow(alice, bob.username)
    assert result.is_following is True
    assert result.followers_count == 1

    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(bob.id, cursor=None, limit=10)
    assert len(page.items) == 1
    assert page.items[0].actor_id == alice.id
    assert page.items[0].type == "follow"


async def test_repeat_follow_is_idempotent_and_creates_no_second_notification(
    db_session: AsyncSession, service: FollowsService
) -> None:
    alice = await _make_user(db_session, "follows_svc_repeat_alice")
    bob = await _make_user(db_session, "follows_svc_repeat_bob")

    await service.follow(alice, bob.username)
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    # A second, identical follow call: still "following", still one follower,
    # and critically no second notification is created.
    result = await service.follow(alice, bob.username)
    assert result.is_following is True
    assert result.followers_count == 1
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(bob.id, cursor=None, limit=10)
    assert len(page.items) == 1


async def test_unfollow_is_idempotent_and_never_notifies(
    db_session: AsyncSession, service: FollowsService
) -> None:
    alice = await _make_user(db_session, "follows_svc_unfollow_alice")
    bob = await _make_user(db_session, "follows_svc_unfollow_bob")

    await service.follow(alice, bob.username)
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    result = await service.unfollow(alice, bob.username)
    assert result.is_following is False
    assert result.followers_count == 0

    # Unfollowing again is a no-op, not an error.
    result_again = await service.unfollow(alice, bob.username)
    assert result_again.is_following is False
    assert result_again.followers_count == 0
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(bob.id, cursor=None, limit=10)
    assert len(page.items) == 1  # only the original follow notification, none for unfollow


async def test_self_follow_and_self_unfollow_are_rejected(
    db_session: AsyncSession, service: FollowsService
) -> None:
    alice = await _make_user(db_session, "follows_svc_self_alice")

    try:
        await service.follow(alice, alice.username)
        raise AssertionError("expected CannotFollowSelfError")
    except CannotFollowSelfError:
        pass

    try:
        await service.unfollow(alice, alice.username)
        raise AssertionError("expected CannotFollowSelfError")
    except CannotFollowSelfError:
        pass


async def test_follow_unknown_user_raises_not_found(
    db_session: AsyncSession, service: FollowsService
) -> None:
    alice = await _make_user(db_session, "follows_svc_notfound_alice")

    try:
        await service.follow(alice, "no_such_user_at_all")
        raise AssertionError("expected UserNotFoundError")
    except UserNotFoundError:
        pass


async def test_list_followers_and_following_resolve_users_and_paginate(
    db_session: AsyncSession, service: FollowsService
) -> None:
    target = await _make_user(db_session, "follows_svc_list_target")
    follower_a = await _make_user(db_session, "follows_svc_list_follower_a")
    follower_b = await _make_user(db_session, "follows_svc_list_follower_b")

    await service.follow(follower_a, target.username)
    await service.follow(follower_b, target.username)
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    page_1 = await service.list_followers(target.username, cursor=None, limit=1)
    assert len(page_1.items) == 1
    assert page_1.next_cursor is not None

    cursor = page_1.next_cursor
    page_2 = await service.list_followers(target.username, cursor=cursor, limit=1)
    assert len(page_2.items) == 1
    assert page_2.next_cursor is None

    seen = {page_1.items[0].id, page_2.items[0].id}
    assert seen == {follower_a.id, follower_b.id}

    following_page = await service.list_following(follower_a.username, cursor=None, limit=10)
    assert [user.id for user in following_page.items] == [target.id]


async def test_list_followers_malformed_cursor_is_rejected(
    db_session: AsyncSession, service: FollowsService
) -> None:
    from app.services.follows import InvalidPaginationCursorError

    target = await _make_user(db_session, "follows_svc_badcursor_target")
    try:
        await service.list_followers(target.username, cursor="not-a-valid-cursor", limit=10)
        raise AssertionError("expected InvalidPaginationCursorError")
    except InvalidPaginationCursorError:
        pass


