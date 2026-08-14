"""Integration tests for `/api/v1/tweets/{id}/like` (spec §6.1, §6.3 "Likes").

Mirrors `tests/test_follows.py`'s real-Postgres/real-Redis app/async_client
fixture setup.
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
def _migrated_schema_for_likes() -> None:
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


async def _truncate_like_tables() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, "
                "tweet_media, tweets, users CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
def likes_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="likes-test-secret",
        auth_rate_limit_per_minute=1000,
        tweet_rate_limit_per_minute=1000,
        like_rate_limit_per_minute=1000,
    )


@pytest_asyncio.fixture
async def app(likes_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_like_tables()
    application = create_app(likes_settings)
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


async def _create_tweet(client: AsyncClient, headers: dict[str, str], content: str) -> str:
    response = await client.post("/api/v1/tweets", json={"content": content}, headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_like_and_unlike_are_idempotent_and_update_counts(
    async_client: AsyncClient,
) -> None:
    alice = await _register(
        async_client, username="like_http_alice", email="like_http_alice@example.com"
    )
    bob = await _register(async_client, username="like_http_bob", email="like_http_bob@example.com")
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )

    tweet_id = await _create_tweet(async_client, bob_headers, "hello world")

    like_response = await async_client.post(
        f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers
    )
    assert like_response.status_code == 200, like_response.text
    assert like_response.json() == {"liked": True, "like_count": 1}

    # Repeat like: idempotent, same result, no error, no double count.
    repeat_response = await async_client.post(
        f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers
    )
    assert repeat_response.status_code == 200
    assert repeat_response.json() == {"liked": True, "like_count": 1}

    tweet_response = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=alice_headers)
    assert tweet_response.status_code == 200
    body = tweet_response.json()
    assert body["like_count"] == 1
    assert body["liked_by_viewer"] is True

    # The author never liked it themselves; their view shows liked_by_viewer=False.
    author_view = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=bob_headers)
    assert author_view.json()["liked_by_viewer"] is False

    unlike_response = await async_client.request(
        "DELETE", f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers
    )
    assert unlike_response.status_code == 200
    assert unlike_response.json() == {"liked": False, "like_count": 0}

    # Repeat unlike: idempotent no-op, not an error.
    repeat_unlike = await async_client.request(
        "DELETE", f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers
    )
    assert repeat_unlike.status_code == 200
    assert repeat_unlike.json() == {"liked": False, "like_count": 0}

    after_unlike = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=alice_headers)
    assert after_unlike.json()["like_count"] == 0
    assert after_unlike.json()["liked_by_viewer"] is False


async def test_like_requires_auth_and_tweet_must_exist(async_client: AsyncClient) -> None:
    unauthenticated = await async_client.post(f"/api/v1/tweets/{uuid.uuid4()}/like")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthenticated"

    alice = await _register(
        async_client, username="like_http_missing", email="like_http_missing@example.com"
    )
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(f"/api/v1/tweets/{uuid.uuid4()}/like", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_like_notification_is_delivered_via_the_notifications_api(
    async_client: AsyncClient,
) -> None:
    alice = await _register(
        async_client, username="like_http_notif_alice", email="like_http_notif_alice@example.com"
    )
    bob = await _register(
        async_client, username="like_http_notif_bob", email="like_http_notif_bob@example.com"
    )
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    tweet_id = await _create_tweet(async_client, bob_headers, "notify me")

    response = await async_client.post(f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers)
    assert response.status_code == 200

    notifications_response = await async_client.get("/api/v1/notifications", headers=bob_headers)
    assert notifications_response.status_code == 200
    body = notifications_response.json()
    assert body["unread_count"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["type"] == "like"
    assert body["data"][0]["actor"]["username"] == alice["username"]
    assert body["data"][0]["tweet_id"] == tweet_id

    # Repeat like: no second notification.
    await async_client.post(f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers)
    bob_notifications_after_repeat = await async_client.get(
        "/api/v1/notifications", headers=bob_headers
    )
    assert bob_notifications_after_repeat.json()["unread_count"] == 1

    # Unlike never notifies.
    await async_client.request("DELETE", f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers)
    bob_notifications_after_unlike = await async_client.get(
        "/api/v1/notifications", headers=bob_headers
    )
    assert bob_notifications_after_unlike.json()["unread_count"] == 1


async def test_self_like_creates_no_notification(async_client: AsyncClient) -> None:
    alice = await _register(
        async_client, username="like_http_self_alice", email="like_http_self_alice@example.com"
    )
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )

    tweet_id = await _create_tweet(async_client, alice_headers, "my own tweet")

    response = await async_client.post(f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers)
    assert response.status_code == 200
    assert response.json() == {"liked": True, "like_count": 1}

    notifications_response = await async_client.get("/api/v1/notifications", headers=alice_headers)
    assert notifications_response.json()["unread_count"] == 0


async def test_like_rate_limit_returns_429_with_retry_after(async_client: AsyncClient) -> None:
    alice = await _register(
        async_client,
        username="like_http_ratelimit_alice",
        email="like_http_ratelimit_alice@example.com",
    )

    limited_settings = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="likes-ratelimit-secret",
        auth_rate_limit_per_minute=1000,
        tweet_rate_limit_per_minute=1000,
        like_rate_limit_per_minute=2,
    )
    limited_app = create_app(limited_settings)
    async with limited_app.router.lifespan_context(limited_app):
        transport = ASGITransport(app=limited_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            bob_2 = await _register(
                client,
                username="like_http_ratelimit_bob2",
                email="like_http_ratelimit_bob2@example.com",
            )
            bob_headers_2 = await _auth_headers(
                client, email=bob_2["email"], password=bob_2["password"]
            )
            alice_headers = await _auth_headers(
                client, email=alice["email"], password=alice["password"]
            )

            tweet_ids = [
                await _create_tweet(client, bob_headers_2, f"ratelimit tweet {i}") for i in range(3)
            ]

            ok_1 = await client.post(f"/api/v1/tweets/{tweet_ids[0]}/like", headers=alice_headers)
            assert ok_1.status_code == 200
            ok_2 = await client.post(f"/api/v1/tweets/{tweet_ids[1]}/like", headers=alice_headers)
            assert ok_2.status_code == 200

            limited = await client.post(
                f"/api/v1/tweets/{tweet_ids[2]}/like", headers=alice_headers
            )
            assert limited.status_code == 429
            assert limited.json()["error"]["code"] == "rate_limited"
            assert "Retry-After" in limited.headers


async def test_concurrent_duplicate_like_requests_are_idempotent(
    async_client: AsyncClient,
) -> None:
    """A burst of concurrent `POST /like` calls for the same tweet (each
    riding its own request-scoped DB session, a genuine concurrency race —
    not merely a sequential repeat call) leaves exactly one like row,
    `like_count == 1`, and exactly one notification.
    """
    alice = await _register(
        async_client, username="like_http_race_alice", email="like_http_race_alice@example.com"
    )
    bob = await _register(
        async_client, username="like_http_race_bob", email="like_http_race_bob@example.com"
    )
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    tweet_id = await _create_tweet(async_client, bob_headers, "race me")

    responses = await asyncio.gather(
        *(
            async_client.post(f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers)
            for _ in range(5)
        )
    )
    for response in responses:
        assert response.status_code == 200
        assert response.json()["liked"] is True

    tweet_response = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=alice_headers)
    assert tweet_response.json()["like_count"] == 1

    notifications_response = await async_client.get("/api/v1/notifications", headers=bob_headers)
    assert notifications_response.json()["unread_count"] == 1


async def test_concurrent_like_and_unlike_leave_counters_non_negative(
    async_client: AsyncClient,
) -> None:
    """A burst of interleaved like/unlike calls for the same tweet must
    never drive `like_count` negative and must always land on a state
    consistent with the actual `likes` row (0 or 1, never anything else).
    """
    alice = await _register(
        async_client,
        username="like_http_race_mixed_alice",
        email="like_http_race_mixed_alice@example.com",
    )
    bob = await _register(
        async_client,
        username="like_http_race_mixed_bob",
        email="like_http_race_mixed_bob@example.com",
    )
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    tweet_id = await _create_tweet(async_client, bob_headers, "mixed race")

    like_response = await async_client.post(
        f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers
    )
    assert like_response.status_code == 200

    async def _like() -> object:
        return await async_client.post(f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers)

    async def _unlike() -> object:
        return await async_client.request(
            "DELETE", f"/api/v1/tweets/{tweet_id}/like", headers=alice_headers
        )

    calls = [_like(), _unlike(), _like(), _unlike(), _unlike(), _like()]
    responses = await asyncio.gather(*calls)
    for response in responses:
        assert response.status_code == 200  # type: ignore[attr-defined]

    tweet_response = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=alice_headers)
    like_count = tweet_response.json()["like_count"]
    assert like_count in (0, 1)
    assert like_count >= 0
