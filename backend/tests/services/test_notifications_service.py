"""Integration tests for `NotificationsService` against a real PostgreSQL
session and a real Redis pub/sub channel (spec §4.2).

These tests drive the commit/rollback lifecycle manually (`session.commit()`
/ `session.rollback()` + `run_post_commit_callbacks`) rather than through
HTTP, mirroring exactly what `get_db_session` (`app.core.deps`) does for a
real request — see `tests/core/test_deps_post_commit.py` for the generic
platform-level version of the same guarantee, and `tests/test_notifications.py`
for the HTTP-level list/mark-read contract.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.outbox import run_post_commit_callbacks
from app.models.notification import NotificationType
from app.models.user import User
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRepository
from app.services.notification_publisher import notification_channel
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
async def service(db_session: AsyncSession, redis_client: Redis) -> NotificationsService:
    return NotificationsService(
        NotificationRepository(db_session), UserRepository(db_session), db_session, redis_client
    )


async def _drain_one(pubsub: PubSub, *, timeout: float) -> dict[str, object] | None:
    """Poll for one pub/sub message up to `timeout` seconds total."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        message = await pubsub.get_message(timeout=0.1)
        if message is not None:
            return cast(dict[str, object], message)
    return None


async def test_publish_happens_only_after_commit_and_matches_the_envelope(
    db_session: AsyncSession, redis_client: Redis, service: NotificationsService
) -> None:
    recipient = await _make_user(db_session, "notif_svc_recipient")
    actor = await _make_user(db_session, "notif_svc_actor")

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(notification_channel(recipient.id))
    try:
        notification = await service.create_notification(
            recipient_id=recipient.id, actor=actor, type_=NotificationType.FOLLOW, tweet_id=None
        )
        assert notification is not None

        # Flushed, not yet committed: nothing published yet.
        assert await _drain_one(pubsub, timeout=0.3) is None

        await db_session.commit()
        await run_post_commit_callbacks(db_session)

        message = await _drain_one(pubsub, timeout=2.0)
        assert message is not None
        payload = json.loads(message["data"])  # type: ignore[arg-type]

        assert payload["type"] == "notification"
        assert payload["event"] == "follow"
        data = payload["data"]
        assert data["notification_id"] == str(notification.id)
        assert data["recipient_id"] == str(recipient.id)
        assert data["actor"] == {
            "id": str(actor.id),
            "username": actor.username,
            "name": actor.name,
            "avatar_key": None,
        }
        assert data["tweet_id"] is None
        assert data["is_read"] is False
        assert data["created_at"]  # ISO timestamp present
    finally:
        await pubsub.aclose()  # type: ignore[no-untyped-call]


async def test_notification_id_in_the_event_matches_the_persisted_row(
    db_session: AsyncSession, redis_client: Redis, service: NotificationsService
) -> None:
    """The id a client de-duplicates by (spec §4.2) is the same id a
    `GET /notifications` fetch would return for this row.
    """
    recipient = await _make_user(db_session, "notif_svc_dedup_recipient")
    actor = await _make_user(db_session, "notif_svc_dedup_actor")

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(notification_channel(recipient.id))
    try:
        notification = await service.create_notification(
            recipient_id=recipient.id, actor=actor, type_=NotificationType.LIKE, tweet_id=None
        )
        assert notification is not None
        await db_session.commit()
        await run_post_commit_callbacks(db_session)

        message = await _drain_one(pubsub, timeout=2.0)
        assert message is not None
        payload = json.loads(message["data"])  # type: ignore[arg-type]

        page = await service.list_for_recipient(recipient, cursor=None, limit=10)
        assert len(page.items) == 1
        assert str(page.items[0].notification.id) == payload["data"]["notification_id"]
        assert payload["data"]["notification_id"] == str(notification.id)
    finally:
        await pubsub.aclose()  # type: ignore[no-untyped-call]


async def test_rollback_publishes_nothing(
    db_session: AsyncSession, redis_client: Redis, service: NotificationsService
) -> None:
    recipient = await _make_user(db_session, "notif_svc_rollback_recipient")
    actor = await _make_user(db_session, "notif_svc_rollback_actor")
    await db_session.commit()  # persist the users themselves first

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(notification_channel(recipient.id))
    try:
        notification = await service.create_notification(
            recipient_id=recipient.id, actor=actor, type_=NotificationType.REPLY, tweet_id=None
        )
        assert notification is not None

        await db_session.rollback()  # the transaction never commits...
        # ...so the queued callback is never drained, and nothing publishes.
        assert await _drain_one(pubsub, timeout=0.5) is None
    finally:
        await pubsub.aclose()  # type: ignore[no-untyped-call]


async def test_self_notification_is_a_noop(
    db_session: AsyncSession, redis_client: Redis, service: NotificationsService
) -> None:
    user = await _make_user(db_session, "notif_svc_self")

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(notification_channel(user.id))
    try:
        notification = await service.create_notification(
            recipient_id=user.id, actor=user, type_=NotificationType.LIKE, tweet_id=None
        )
        assert notification is None

        await db_session.commit()
        await run_post_commit_callbacks(db_session)
        assert await _drain_one(pubsub, timeout=0.3) is None
        assert await service.count_unread(user) == 0
    finally:
        await pubsub.aclose()  # type: ignore[no-untyped-call]


async def test_list_for_recipient_resolves_actor_and_is_scoped(
    db_session: AsyncSession, redis_client: Redis, service: NotificationsService
) -> None:
    recipient = await _make_user(db_session, "notif_svc_list_recipient")
    other_recipient = await _make_user(db_session, "notif_svc_list_other")
    actor = await _make_user(db_session, "notif_svc_list_actor")

    await service.create_notification(
        recipient_id=recipient.id, actor=actor, type_=NotificationType.FOLLOW, tweet_id=None
    )
    await service.create_notification(
        recipient_id=other_recipient.id, actor=actor, type_=NotificationType.FOLLOW, tweet_id=None
    )
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    page = await service.list_for_recipient(recipient, cursor=None, limit=10)
    assert len(page.items) == 1
    assert page.items[0].notification.recipient_id == recipient.id
    assert page.items[0].actor.id == actor.id
    assert page.items[0].actor.username == actor.username
