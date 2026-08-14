"""Integration tests for `GET /api/v1/feed` (spec §6.3 "Tweets & feed",
§8.2 "Feed generation (fan-out on read)"). Mirrors `tests/test_tweets.py`'s
real-Postgres/real-Redis app/async_client fixture setup.
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
def _migrated_schema_for_feed() -> None:
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


async def _truncate_tables() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, "
                "tweet_media, tweets, pending_uploads, users CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
def feed_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="feed-test-secret",
        auth_rate_limit_per_minute=1000,
        tweet_rate_limit_per_minute=1000,
        follow_rate_limit_per_minute=1000,
        feed_cache_ttl_seconds=30,
    )


@pytest_asyncio.fixture
async def app(feed_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_tables()
    application = create_app(feed_settings)
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
        "username": f"fd{suffix}",
        "email": f"fd{suffix}@example.com",
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


async def _register_and_login(client: AsyncClient) -> tuple[dict[str, str], dict[str, str]]:
    user = await _register(client)
    headers = await _auth_headers(client, email=user["email"], password=user["password"])
    return user, headers


async def _tweet(client: AsyncClient, headers: dict[str, str], content: str) -> str:
    response = await client.post("/api/v1/tweets", headers=headers, json={"content": content})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _follow(client: AsyncClient, headers: dict[str, str], username: str) -> None:
    response = await client.post(f"/api/v1/users/{username}/follow", headers=headers)
    assert response.status_code == 200, response.text


# --- membership & auth ----------------------------------------------------------


async def test_feed_requires_auth(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/feed")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_feed_contains_own_and_followed_tweets_but_not_unrelated_ones(
    async_client: AsyncClient,
) -> None:
    alice, alice_headers = await _register_and_login(async_client)
    bob, bob_headers = await _register_and_login(async_client)
    carol, carol_headers = await _register_and_login(async_client)

    await _follow(async_client, alice_headers, bob["username"])

    own_id = await _tweet(async_client, alice_headers, "alice's own post")
    followed_id = await _tweet(async_client, bob_headers, "bob's post")
    unrelated_id = await _tweet(async_client, carol_headers, "carol's post")

    response = await async_client.get("/api/v1/feed", headers=alice_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    ids = {item["id"] for item in body["data"]}
    assert own_id in ids
    assert followed_id in ids
    assert unrelated_id not in ids
    # newest first
    assert body["data"][0]["id"] == followed_id
    assert body["data"][1]["id"] == own_id


async def test_feed_is_empty_when_following_no_one_and_no_own_tweets(
    async_client: AsyncClient,
) -> None:
    _, headers = await _register_and_login(async_client)
    response = await async_client.get("/api/v1/feed", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"data": [], "page": {"next_cursor": None}}


# --- pagination -------------------------------------------------------------


async def test_feed_rejects_limit_above_50(async_client: AsyncClient) -> None:
    _, headers = await _register_and_login(async_client)
    response = await async_client.get("/api/v1/feed?limit=51", headers=headers)
    assert response.status_code == 422


async def test_feed_rejects_malformed_cursor(async_client: AsyncClient) -> None:
    _, headers = await _register_and_login(async_client)
    response = await async_client.get("/api/v1/feed?cursor=not-valid", headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


async def test_feed_paginates_without_duplicates_or_skips(async_client: AsyncClient) -> None:
    alice, alice_headers = await _register_and_login(async_client)
    posted_ids = []
    for i in range(25):
        posted_ids.append(await _tweet(async_client, alice_headers, f"post {i}"))

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        url = "/api/v1/feed?limit=10"
        if cursor:
            url += f"&cursor={cursor}"
        response = await async_client.get(url, headers=alice_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(item["id"] for item in body["data"])
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(posted_ids))
    assert len(seen) == len(set(seen))


# --- concurrency --------------------------------------------------------------


async def test_feed_has_no_duplicate_or_missing_items_under_concurrent_inserts(
    async_client: AsyncClient,
) -> None:
    alice, alice_headers = await _register_and_login(async_client)
    bob, bob_headers = await _register_and_login(async_client)
    await _follow(async_client, alice_headers, bob["username"])

    async def _post(i: int) -> str:
        response = await async_client.post(
            "/api/v1/tweets", headers=bob_headers, json={"content": f"concurrent {i}"}
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    posted_ids = set(await asyncio.gather(*(_post(i) for i in range(10))))

    seen: set[str] = set()
    cursor = None
    for _ in range(10):
        url = "/api/v1/feed?limit=5"
        if cursor:
            url += f"&cursor={cursor}"
        response = await async_client.get(url, headers=alice_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        for item in body["data"]:
            assert item["id"] not in seen, "duplicate item across feed pages"
            seen.add(item["id"])
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            break

    assert posted_ids <= seen


# --- cache ----------------------------------------------------------------------


async def test_feed_first_page_is_cached_briefly_and_isolated_per_user(
    async_client: AsyncClient,
) -> None:
    alice, alice_headers = await _register_and_login(async_client)
    bob, bob_headers = await _register_and_login(async_client)

    await _tweet(async_client, alice_headers, "alice's cached tweet")

    first = await async_client.get("/api/v1/feed", headers=alice_headers)
    assert len(first.json()["data"]) == 1

    # A new tweet posted right after must not appear in alice's cached
    # first page (within the TTL window smoothing infinite-scroll refreshes).
    await _tweet(async_client, alice_headers, "alice's second tweet")
    still_cached = await async_client.get("/api/v1/feed", headers=alice_headers)
    assert len(still_cached.json()["data"]) == 1
    assert still_cached.json()["data"][0]["id"] == first.json()["data"][0]["id"]

    # Bob's own feed is never affected by alice's cache entry.
    bob_feed = await async_client.get("/api/v1/feed", headers=bob_headers)
    assert bob_feed.json()["data"] == []
