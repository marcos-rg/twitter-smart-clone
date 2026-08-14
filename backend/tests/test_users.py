"""Integration tests for `/api/v1/users/*` profile, timeline, and search APIs."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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
from app.models.tweet import Tweet
from app.repositories.users import UserRepository
from tests.repositories.conftest import _alembic_config

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_users() -> None:
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


async def _truncate_user_tables() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, tweet_media, tweets, users CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
def users_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret_key="users-test-secret",
        auth_rate_limit_per_minute=1000,
    )


@pytest_asyncio.fixture
async def app(users_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_user_tables()
    application = create_app(users_settings)
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


async def _create_tweet_for_user(username: str, content: str, created_at: datetime) -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        user = await UserRepository(session).get_by_username(username)
        assert user is not None
        session.add(Tweet(author_id=user.id, content=content, created_at=created_at))
        await session.commit()
    await engine.dispose()


async def test_public_profile_lookup_is_case_insensitive_and_private_safe(
    async_client: AsyncClient,
) -> None:
    owner = await _register(
        async_client, username="profile_owner", email="profile_owner@example.com"
    )
    viewer = await _register(
        async_client, username="profile_viewer", email="profile_viewer@example.com"
    )
    headers = await _auth_headers(async_client, email=viewer["email"], password=viewer["password"])

    response = await async_client.get("/api/v1/users/PROFILE_OWNER", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == owner["username"]
    assert "email" not in data
    assert "password_hash" not in data


async def test_only_current_user_can_edit_profile_and_conflicts_are_deterministic(
    async_client: AsyncClient,
) -> None:
    user = await _register(
        async_client, username="editable_user", email="editable_user@example.com"
    )
    other = await _register(async_client, username="taken_user", email="taken_user@example.com")
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    response = await async_client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"username": other["username"], "email": other["email"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Username is already taken."

    update_response = await async_client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={
            "name": "Updated Name",
            "username": "updated_user",
            "email": "updated_user@example.com",
            "bio": "updated bio",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Updated Name"
    assert updated["username"] == "updated_user"
    assert updated["email"] == "updated_user@example.com"
    assert updated["bio"] == "updated bio"


async def test_profile_update_requires_auth_and_validates_fields(async_client: AsyncClient) -> None:
    response = await async_client.patch("/api/v1/users/me", json={"bio": "no auth"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"

    user = await _register(
        async_client, username="validator_user", email="validator_user@example.com"
    )
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])
    invalid = await async_client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"username": "no spaces allowed!", "bio": "x" * 161},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "semantic_validation_error"


async def test_profile_timeline_paginates_and_rejects_malformed_cursor(
    async_client: AsyncClient,
) -> None:
    owner = await _register(
        async_client, username="timeline_user", email="timeline_user@example.com"
    )
    viewer = await _register(
        async_client, username="timeline_viewer", email="timeline_viewer@example.com"
    )
    headers = await _auth_headers(async_client, email=viewer["email"], password=viewer["password"])

    base = datetime.now(UTC)
    await _create_tweet_for_user(owner["username"], "tweet-1", base + timedelta(seconds=1))
    await _create_tweet_for_user(owner["username"], "tweet-2", base + timedelta(seconds=2))
    await _create_tweet_for_user(owner["username"], "tweet-3", base + timedelta(seconds=3))

    page_1 = await async_client.get(
        f"/api/v1/users/{owner['username']}/tweets",
        headers=headers,
        params={"limit": 2},
    )
    assert page_1.status_code == 200
    body_1 = page_1.json()
    assert [item["content"] for item in body_1["data"]] == ["tweet-3", "tweet-2"]
    assert body_1["page"]["next_cursor"] is not None

    page_2 = await async_client.get(
        f"/api/v1/users/{owner['username']}/tweets",
        headers=headers,
        params={"limit": 2, "cursor": body_1["page"]["next_cursor"]},
    )
    assert page_2.status_code == 200
    body_2 = page_2.json()
    assert [item["content"] for item in body_2["data"]] == ["tweet-1"]
    assert body_2["page"]["next_cursor"] is None

    malformed = await async_client.get(
        f"/api/v1/users/{owner['username']}/tweets",
        headers=headers,
        params={"cursor": "this-is-not-a-valid-cursor"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "validation_error"


async def test_search_supports_exact_prefix_fuzzy_and_cursor(async_client: AsyncClient) -> None:
    await _register(
        async_client, name="Ada Lovelace", username="ada_exact", email="ada_exact@example.com"
    )
    await _register(
        async_client, name="Alice", username="alice_prefix", email="alice_prefix@example.com"
    )
    await _register(
        async_client, name="Albert", username="albert_prefix", email="albert_prefix@example.com"
    )
    await _register(
        async_client,
        name="Searchable Ada",
        username="searchable_ada",
        email="searchable_ada@example.com",
    )
    viewer = await _register(
        async_client, username="search_viewer", email="search_viewer@example.com"
    )
    headers = await _auth_headers(async_client, email=viewer["email"], password=viewer["password"])

    exact = await async_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"q": "ADA_EXACT", "mode": "exact"},
    )
    assert exact.status_code == 200
    exact_data = exact.json()["data"]
    assert exact_data
    assert exact_data[0]["username"] == "ada_exact"

    prefix_page_1 = await async_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"q": "al", "mode": "prefix", "limit": 1},
    )
    assert prefix_page_1.status_code == 200
    page_1_body = prefix_page_1.json()
    assert len(page_1_body["data"]) == 1
    assert page_1_body["page"]["next_cursor"] is not None

    prefix_page_2 = await async_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={
            "q": "al",
            "mode": "prefix",
            "limit": 1,
            "cursor": page_1_body["page"]["next_cursor"],
        },
    )
    assert prefix_page_2.status_code == 200
    page_2_body = prefix_page_2.json()
    assert len(page_2_body["data"]) == 1
    assert page_1_body["data"][0]["username"] != page_2_body["data"][0]["username"]

    fuzzy = await async_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"q": "serchable", "mode": "fuzzy"},
    )
    assert fuzzy.status_code == 200
    assert any(item["username"] == "searchable_ada" for item in fuzzy.json()["data"])

    malformed_cursor = await async_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"q": "al", "mode": "prefix", "cursor": "not-valid"},
    )
    assert malformed_cursor.status_code == 400
    assert malformed_cursor.json()["error"]["code"] == "validation_error"
