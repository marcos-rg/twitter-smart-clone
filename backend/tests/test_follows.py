"""Integration tests for `/api/v1/users/{username}/follow`, `/followers`,
and `/following` (spec §6.1, §6.3 "Follows").
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import Settings
from app.main import create_app
from tests.repositories.conftest import _alembic_config

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_follows() -> None:
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


async def _truncate_follow_tables() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, tweet_media, tweets, users CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
def follows_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="follows-test-secret",
        auth_rate_limit_per_minute=1000,
        follow_rate_limit_per_minute=1000,
    )


@pytest_asyncio.fixture
async def app(follows_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_follow_tables()
    application = create_app(follows_settings)
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


async def test_follow_and_unfollow_are_idempotent_and_update_counts(
    async_client: AsyncClient,
) -> None:
    alice = await _register(
        async_client, username="follow_http_alice", email="follow_http_alice@example.com"
    )
    bob = await _register(
        async_client, username="follow_http_bob", email="follow_http_bob@example.com"
    )
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    follow_response = await async_client.post(
        f"/api/v1/users/{bob['username']}/follow", headers=headers
    )
    assert follow_response.status_code == 200, follow_response.text
    body = follow_response.json()
    assert body == {"following": True, "followers_count": 1}

    # Repeat follow: idempotent, same result, no error.
    repeat_response = await async_client.post(
        f"/api/v1/users/{bob['username']}/follow", headers=headers
    )
    assert repeat_response.status_code == 200
    assert repeat_response.json() == {"following": True, "followers_count": 1}

    profile_response = await async_client.get(f"/api/v1/users/{bob['username']}", headers=headers)
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["followers_count"] == 1
    assert profile["following_count"] == 0

    viewer_profile = await async_client.get(f"/api/v1/users/{alice['username']}", headers=headers)
    assert viewer_profile.json()["following_count"] == 1

    unfollow_response = await async_client.request(
        "DELETE", f"/api/v1/users/{bob['username']}/follow", headers=headers
    )
    assert unfollow_response.status_code == 200
    assert unfollow_response.json() == {"following": False, "followers_count": 0}

    # Repeat unfollow: idempotent no-op, not an error.
    repeat_unfollow = await async_client.request(
        "DELETE", f"/api/v1/users/{bob['username']}/follow", headers=headers
    )
    assert repeat_unfollow.status_code == 200
    assert repeat_unfollow.json() == {"following": False, "followers_count": 0}


async def test_cannot_follow_self(async_client: AsyncClient) -> None:
    alice = await _register(
        async_client, username="follow_http_self", email="follow_http_self@example.com"
    )
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(f"/api/v1/users/{alice['username']}/follow", headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "semantic_validation_error"

    delete_response = await async_client.request(
        "DELETE", f"/api/v1/users/{alice['username']}/follow", headers=headers
    )
    assert delete_response.status_code == 422


async def test_follow_requires_auth_and_target_must_exist(async_client: AsyncClient) -> None:
    unauthenticated = await async_client.post("/api/v1/users/someone/follow")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthenticated"

    alice = await _register(
        async_client, username="follow_http_missing", email="follow_http_missing@example.com"
    )
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post("/api/v1/users/no_such_user_xyz/follow", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_followers_and_following_lists_paginate_without_duplicates(
    async_client: AsyncClient,
) -> None:
    target = await _register(
        async_client,
        username="follow_http_list_target",
        email="follow_http_list_target@example.com",
    )
    follower_users = []
    for i in range(3):
        follower_users.append(
            await _register(
                async_client,
                username=f"follow_http_list_follower_{i}",
                email=f"follow_http_list_follower_{i}@example.com",
            )
        )

    for follower in follower_users:
        headers = await _auth_headers(
            async_client, email=follower["email"], password=follower["password"]
        )
        response = await async_client.post(
            f"/api/v1/users/{target['username']}/follow", headers=headers
        )
        assert response.status_code == 200

    viewer_headers = await _auth_headers(
        async_client, email=target["email"], password=target["password"]
    )

    page_1 = await async_client.get(
        f"/api/v1/users/{target['username']}/followers",
        headers=viewer_headers,
        params={"limit": 2},
    )
    assert page_1.status_code == 200
    body_1 = page_1.json()
    assert len(body_1["data"]) == 2
    assert body_1["page"]["next_cursor"] is not None

    page_2 = await async_client.get(
        f"/api/v1/users/{target['username']}/followers",
        headers=viewer_headers,
        params={"limit": 2, "cursor": body_1["page"]["next_cursor"]},
    )
    assert page_2.status_code == 200
    body_2 = page_2.json()
    assert len(body_2["data"]) == 1
    assert body_2["page"]["next_cursor"] is None

    all_usernames = [item["username"] for item in body_1["data"] + body_2["data"]]
    assert set(all_usernames) == {follower["username"] for follower in follower_users}
    assert len(all_usernames) == len(set(all_usernames))  # no duplicates across pages

    malformed = await async_client.get(
        f"/api/v1/users/{target['username']}/followers",
        headers=viewer_headers,
        params={"cursor": "not-a-valid-cursor"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "validation_error"

    following_response = await async_client.get(
        f"/api/v1/users/{follower_users[0]['username']}/following", headers=viewer_headers
    )
    assert following_response.status_code == 200
    following_data = following_response.json()["data"]
    assert [item["username"] for item in following_data] == [target["username"]]


async def test_follow_notification_is_delivered_via_the_notifications_api(
    async_client: AsyncClient,
) -> None:
    alice = await _register(
        async_client,
        username="follow_http_notif_alice",
        email="follow_http_notif_alice@example.com",
    )
    bob = await _register(
        async_client, username="follow_http_notif_bob", email="follow_http_notif_bob@example.com"
    )
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    response = await async_client.post(
        f"/api/v1/users/{bob['username']}/follow", headers=alice_headers
    )
    assert response.status_code == 200

    notifications_response = await async_client.get("/api/v1/notifications", headers=bob_headers)
    assert notifications_response.status_code == 200
    body = notifications_response.json()
    assert body["unread_count"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["type"] == "follow"
    assert body["data"][0]["actor"]["username"] == alice["username"]

    # Alice never notifies herself, and unfollowing creates nothing.
    alice_notifications = await async_client.get("/api/v1/notifications", headers=alice_headers)
    assert alice_notifications.json()["unread_count"] == 0

    unfollow_response = await async_client.request(
        "DELETE", f"/api/v1/users/{bob['username']}/follow", headers=alice_headers
    )
    assert unfollow_response.status_code == 200
    bob_notifications_after_unfollow = await async_client.get(
        "/api/v1/notifications", headers=bob_headers
    )
    assert bob_notifications_after_unfollow.json()["unread_count"] == 1  # unchanged by unfollow


async def test_follow_rate_limit_returns_429_with_retry_after(async_client: AsyncClient) -> None:
    alice = await _register(
        async_client,
        username="follow_http_ratelimit_alice",
        email="follow_http_ratelimit_alice@example.com",
    )

    limited_settings = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="follows-ratelimit-secret",
        auth_rate_limit_per_minute=1000,
        follow_rate_limit_per_minute=2,
    )
    limited_app = create_app(limited_settings)
    async with limited_app.router.lifespan_context(limited_app):
        transport = ASGITransport(app=limited_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            targets = []
            for i in range(3):
                targets.append(
                    await _register(
                        client,
                        username=f"follow_http_ratelimit_target_{i}",
                        email=f"follow_http_ratelimit_target_{i}@example.com",
                    )
                )
            alice_headers = await _auth_headers(
                client, email=alice["email"], password=alice["password"]
            )

            ok_1 = await client.post(
                f"/api/v1/users/{targets[0]['username']}/follow", headers=alice_headers
            )
            assert ok_1.status_code == 200
            ok_2 = await client.post(
                f"/api/v1/users/{targets[1]['username']}/follow", headers=alice_headers
            )
            assert ok_2.status_code == 200

            limited = await client.post(
                f"/api/v1/users/{targets[2]['username']}/follow", headers=alice_headers
            )
            assert limited.status_code == 429
            assert limited.json()["error"]["code"] == "rate_limited"
            assert "Retry-After" in limited.headers


async def test_concurrent_duplicate_follow_requests_are_idempotent(
    async_client: AsyncClient,
) -> None:
    """A burst of concurrent `POST /follow` calls for the same pair (each
    riding its own request-scoped DB session, a genuine concurrency race —
    not merely a sequential repeat call) leaves exactly one follow edge and
    exactly one notification.
    """
    alice = await _register(
        async_client, username="follow_http_race_alice", email="follow_http_race_alice@example.com"
    )
    bob = await _register(
        async_client, username="follow_http_race_bob", email="follow_http_race_bob@example.com"
    )
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    responses = await asyncio.gather(
        *(
            async_client.post(f"/api/v1/users/{bob['username']}/follow", headers=alice_headers)
            for _ in range(5)
        )
    )
    for response in responses:
        assert response.status_code == 200
        assert response.json()["following"] is True

    profile = await async_client.get(f"/api/v1/users/{bob['username']}", headers=alice_headers)
    assert profile.json()["followers_count"] == 1

    notifications_response = await async_client.get("/api/v1/notifications", headers=bob_headers)
    assert notifications_response.json()["unread_count"] == 1
