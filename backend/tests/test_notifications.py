"""Integration tests for `/api/v1/notifications/*` list and mark-read APIs
(`TSC-NOTIF-001`, spec §4.2, §6.1).

Notification *creation* has no public REST endpoint in this task (trigger
wiring belongs to the follow/like/reply tasks), so these tests seed rows
directly against the database, mirroring `test_users.py`'s
`_create_tweet_for_user` helper, and focus on what this task actually owns:
authorization scoping, cursor pagination, and mark-read idempotency.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic import command
from app.core.config import Settings
from app.main import create_app
from app.models.notification import Notification, NotificationType
from app.repositories.users import UserRepository
from tests.repositories.conftest import _alembic_config

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_notifications() -> None:
    command.upgrade(_alembic_config(), "head")


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://twitter_smart_clone:twitter_smart_clone_dev"
        "@localhost:5432/twitter_smart_clone",
    ),
)


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


async def _truncate_notification_tables() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, tweet_media, "
                "tweets, users CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
def notifications_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="notifications-test-secret",
        auth_rate_limit_per_minute=1000,
    )


@pytest_asyncio.fixture
async def app(notifications_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_notification_tables()
    application = create_app(notifications_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _register(client: AsyncClient, **overrides: str) -> dict[str, str]:
    suffix = _unique_suffix()
    payload = {
        "name": "Ada Lovelace",
        "username": f"ada{suffix}",
        "email": f"ada{suffix}@example.com",
        "password": "correct horse battery staple",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


async def _auth_headers(client: AsyncClient, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_notification(
    *,
    recipient_username: str,
    actor_username: str,
    type_: NotificationType = NotificationType.FOLLOW,
    created_at: datetime | None = None,
    is_read: bool = False,
) -> UUID:
    """Insert one notification row directly, bypassing the (not-yet-public)
    creation path, so list/mark-read can be tested against known rows.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        users = UserRepository(session)
        recipient = await users.get_by_username(recipient_username)
        actor = await users.get_by_username(actor_username)
        assert recipient is not None
        assert actor is not None
        notification = Notification(
            recipient_id=recipient.id,
            actor_id=actor.id,
            type=type_,
            tweet_id=None,
            is_read=is_read,
            **({"created_at": created_at} if created_at is not None else {}),
        )
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
        notification_id = notification.id
    await engine.dispose()
    return notification_id


async def test_list_requires_auth(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/notifications")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_mark_read_requires_auth(async_client: AsyncClient) -> None:
    response = await async_client.post("/api/v1/notifications/read", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_recipient_only_sees_their_own_notifications_with_accurate_unread_state(
    async_client: AsyncClient,
) -> None:
    owner = await _register(async_client, username="notif_owner", email="notif_owner@example.com")
    other = await _register(async_client, username="notif_other", email="notif_other@example.com")
    actor = await _register(
        async_client, username="notif_actor_a", email="notif_actor_a@example.com"
    )

    await _seed_notification(recipient_username=owner["username"], actor_username=actor["username"])
    await _seed_notification(recipient_username=other["username"], actor_username=actor["username"])

    owner_headers = await _auth_headers(
        async_client, email=owner["email"], password=owner["password"]
    )
    other_headers = await _auth_headers(
        async_client, email=other["email"], password=other["password"]
    )

    owner_response = await async_client.get("/api/v1/notifications", headers=owner_headers)
    assert owner_response.status_code == 200
    owner_body = owner_response.json()
    assert len(owner_body["data"]) == 1
    assert owner_body["data"][0]["actor"]["username"] == actor["username"]
    assert owner_body["data"][0]["is_read"] is False
    assert owner_body["unread_count"] == 1

    other_response = await async_client.get("/api/v1/notifications", headers=other_headers)
    other_body = other_response.json()
    assert len(other_body["data"]) == 1
    assert other_body["data"][0]["id"] != owner_body["data"][0]["id"]
    assert other_body["unread_count"] == 1


async def test_list_pagination_is_stable_and_malformed_cursor_is_rejected(
    async_client: AsyncClient,
) -> None:
    owner = await _register(
        async_client, username="notif_page_owner", email="notif_page_owner@example.com"
    )
    actor = await _register(
        async_client, username="notif_page_actor", email="notif_page_actor@example.com"
    )
    headers = await _auth_headers(async_client, email=owner["email"], password=owner["password"])

    base = datetime.now(UTC)
    ids = []
    for i in range(3):
        notification_id = await _seed_notification(
            recipient_username=owner["username"],
            actor_username=actor["username"],
            created_at=base + timedelta(seconds=i),
        )
        ids.append(str(notification_id))
    # Seeded oldest→newest; the API returns newest first.
    expected_newest_first = list(reversed(ids))

    page_1 = await async_client.get("/api/v1/notifications", headers=headers, params={"limit": 2})
    assert page_1.status_code == 200
    body_1 = page_1.json()
    assert [item["id"] for item in body_1["data"]] == expected_newest_first[:2]
    assert body_1["page"]["next_cursor"] is not None

    page_2 = await async_client.get(
        "/api/v1/notifications",
        headers=headers,
        params={"limit": 2, "cursor": body_1["page"]["next_cursor"]},
    )
    assert page_2.status_code == 200
    body_2 = page_2.json()
    assert [item["id"] for item in body_2["data"]] == expected_newest_first[2:]
    assert body_2["page"]["next_cursor"] is None

    # Cursor stability: re-requesting page 1 with the same cursor/limit
    # returns the identical set, not a shifted window.
    page_1_again = await async_client.get(
        "/api/v1/notifications", headers=headers, params={"limit": 2}
    )
    assert [item["id"] for item in page_1_again.json()["data"]] == expected_newest_first[:2]

    malformed = await async_client.get(
        "/api/v1/notifications",
        headers=headers,
        params={"cursor": "not-a-valid-cursor"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "validation_error"


async def test_mark_all_read_is_idempotent(async_client: AsyncClient) -> None:
    owner = await _register(
        async_client, username="notif_markall_owner", email="notif_markall_owner@example.com"
    )
    actor = await _register(
        async_client, username="notif_markall_actor", email="notif_markall_actor@example.com"
    )
    headers = await _auth_headers(async_client, email=owner["email"], password=owner["password"])

    for _ in range(3):
        await _seed_notification(
            recipient_username=owner["username"], actor_username=actor["username"]
        )

    first = await async_client.post("/api/v1/notifications/read", headers=headers, json={})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["marked_read"] == 3
    assert first_body["unread_count"] == 0

    listing = await async_client.get("/api/v1/notifications", headers=headers)
    assert all(item["is_read"] for item in listing.json()["data"])
    assert listing.json()["unread_count"] == 0

    # Idempotent: calling again marks nothing new and unread stays 0.
    second = await async_client.post("/api/v1/notifications/read", headers=headers, json={})
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["marked_read"] == 0
    assert second_body["unread_count"] == 0


async def test_mark_selected_read_is_idempotent_and_scoped_to_the_caller(
    async_client: AsyncClient,
) -> None:
    owner = await _register(
        async_client, username="notif_select_owner", email="notif_select_owner@example.com"
    )
    other = await _register(
        async_client, username="notif_select_other", email="notif_select_other@example.com"
    )
    actor = await _register(
        async_client, username="notif_select_actor", email="notif_select_actor@example.com"
    )
    owner_headers = await _auth_headers(
        async_client, email=owner["email"], password=owner["password"]
    )
    other_headers = await _auth_headers(
        async_client, email=other["email"], password=other["password"]
    )

    id_a = await _seed_notification(
        recipient_username=owner["username"], actor_username=actor["username"]
    )
    id_b = await _seed_notification(
        recipient_username=owner["username"], actor_username=actor["username"]
    )
    other_id = await _seed_notification(
        recipient_username=other["username"], actor_username=actor["username"]
    )

    # Mixing in another user's notification id must not affect their unread
    # state, and must not error (no enumeration signal either way).
    response = await async_client.post(
        "/api/v1/notifications/read",
        headers=owner_headers,
        json={"notification_ids": [str(id_a), str(other_id)]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["marked_read"] == 1
    assert body["unread_count"] == 1  # id_b still unread

    other_listing = await async_client.get("/api/v1/notifications", headers=other_headers)
    assert other_listing.json()["unread_count"] == 1
    assert other_listing.json()["data"][0]["id"] == str(other_id)
    assert other_listing.json()["data"][0]["is_read"] is False

    # Idempotent: re-marking id_a again matches nothing new.
    repeat = await async_client.post(
        "/api/v1/notifications/read",
        headers=owner_headers,
        json={"notification_ids": [str(id_a)]},
    )
    assert repeat.status_code == 200
    assert repeat.json()["marked_read"] == 0

    # Marking the rest clears the owner's unread count.
    finish = await async_client.post(
        "/api/v1/notifications/read",
        headers=owner_headers,
        json={"notification_ids": [str(id_b)]},
    )
    assert finish.status_code == 200
    assert finish.json()["marked_read"] == 1
    assert finish.json()["unread_count"] == 0
