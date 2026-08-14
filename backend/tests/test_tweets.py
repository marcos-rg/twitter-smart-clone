"""Integration tests for `POST /api/v1/tweets`, `GET /api/v1/tweets/{id}`,
`GET /api/v1/tweets/{id}/replies`, and `GET /api/v1/users/{username}/tweets`
(spec §5.1, §5.3, §6.1, §6.3 "Tweets & feed").

Mirrors `tests/test_follows.py`'s real-Postgres/real-Redis app/async_client
fixture setup.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
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

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_tweets() -> None:
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
def tweets_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="tweets-test-secret",
        auth_rate_limit_per_minute=1000,
        tweet_rate_limit_per_minute=1000,
    )


@pytest_asyncio.fixture
async def app(tweets_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_tables()
    application = create_app(tweets_settings)
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
        "username": f"tw{suffix}",
        "email": f"tw{suffix}@example.com",
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


async def _put_object(upload_url: str, *, body: bytes, content_type: str) -> httpx.Response:
    async with httpx.AsyncClient() as raw_client:
        return await raw_client.put(
            upload_url, content=body, headers={"Content-Type": content_type}
        )


async def _confirm_tweet_image(client: AsyncClient, headers: dict[str, str]) -> str:
    """Presign, upload, and confirm one tweet-image, returning its key."""
    presign = await client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "tweet_image",
            "files": [{"content_type": "image/png", "size_bytes": len(PNG_BYTES)}],
        },
    )
    assert presign.status_code == 200, presign.text
    upload = presign.json()["uploads"][0]
    assert urlparse(upload["upload_url"]).hostname == "minio"

    put_response = await _put_object(upload["upload_url"], body=PNG_BYTES, content_type="image/png")
    assert put_response.status_code in (200, 201), put_response.text

    confirm = await client.post(
        "/api/v1/media/confirm",
        headers=headers,
        json={"purpose": "tweet_image", "keys": [upload["key"]]},
    )
    assert confirm.status_code == 200, confirm.text
    return str(upload["key"])


# --- creation ----------------------------------------------------------------


async def test_create_tweet_returns_author_counts_and_empty_media_and_links(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": "hello, world!"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content"] == "hello, world!"
    assert body["author"]["username"] == alice["username"]
    assert body["parent_tweet_id"] is None
    assert body["like_count"] == 0
    assert body["reply_count"] == 0
    assert body["liked_by_viewer"] is False
    assert body["media"] == []
    assert body["links"] == []
    assert "id" in body and "created_at" in body


async def test_create_tweet_requires_auth(async_client: AsyncClient) -> None:
    response = await async_client.post("/api/v1/tweets", json={"content": "no auth"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_create_tweet_rejects_blank_and_whitespace_only_content(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    for bad_content in ["", "   ", "\n\t  \n"]:
        response = await async_client.post(
            "/api/v1/tweets", headers=headers, json={"content": bad_content}
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "semantic_validation_error"


async def test_create_tweet_strips_leading_and_trailing_whitespace(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": "   padded content   "}
    )
    assert response.status_code == 201, response.text
    assert response.json()["content"] == "padded content"


async def test_create_tweet_preserves_internal_whitespace_and_newlines(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    content = "line one\nline  two with  double spaces"
    response = await async_client.post("/api/v1/tweets", headers=headers, json={"content": content})
    assert response.status_code == 201, response.text
    assert response.json()["content"] == content


async def test_create_tweet_rejects_content_over_280_chars_after_stripping(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    too_long = "x" * 281
    response = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": too_long}
    )
    assert response.status_code == 422, response.text

    exactly_280 = "x" * 280
    ok_response = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": exactly_280}
    )
    assert ok_response.status_code == 201, ok_response.text


async def test_create_tweet_rejects_more_than_four_media_keys(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "too many images", "media_keys": ["a", "b", "c", "d", "e"]},
    )
    assert response.status_code == 422, response.text


async def test_create_tweet_with_confirmed_images_orders_and_exposes_them(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    key_1 = await _confirm_tweet_image(async_client, headers)
    key_2 = await _confirm_tweet_image(async_client, headers)

    response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "look at these", "media_keys": [key_1, key_2]},
    )
    assert response.status_code == 201, response.text
    media = response.json()["media"]
    assert [m["key"] for m in media] == [key_1, key_2]
    assert [m["position"] for m in media] == [0, 1]


async def test_create_tweet_rejects_duplicate_media_keys_in_one_request(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])
    key = await _confirm_tweet_image(async_client, headers)

    response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "duplicate key", "media_keys": [key, key]},
    )
    assert response.status_code == 422, response.text


async def test_get_tweet_includes_ordered_media_for_a_tweet_with_images(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])
    key_1 = await _confirm_tweet_image(async_client, headers)
    key_2 = await _confirm_tweet_image(async_client, headers)

    create_response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "with images", "media_keys": [key_1, key_2]},
    )
    tweet_id = create_response.json()["id"]

    get_response = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=headers)
    assert get_response.status_code == 200
    media = get_response.json()["media"]
    assert [m["key"] for m in media] == [key_1, key_2]


async def test_create_tweet_rejects_media_key_owned_by_another_user(
    async_client: AsyncClient,
) -> None:
    owner = await _register(async_client)
    owner_headers = await _auth_headers(
        async_client, email=owner["email"], password=owner["password"]
    )
    key = await _confirm_tweet_image(async_client, owner_headers)

    other = await _register(async_client)
    other_headers = await _auth_headers(
        async_client, email=other["email"], password=other["password"]
    )
    response = await async_client.post(
        "/api/v1/tweets",
        headers=other_headers,
        json={"content": "not my image", "media_keys": [key]},
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "forbidden"


async def test_create_tweet_rejects_reusing_a_media_key_across_tweets(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])
    key = await _confirm_tweet_image(async_client, headers)

    first = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": "first use", "media_keys": [key]}
    )
    assert first.status_code == 201

    second = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": "reused image", "media_keys": [key]}
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "conflict"


# --- safe link data -----------------------------------------------------------


async def test_create_tweet_extracts_safe_link_entities(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "check this out: https://example.com/page neat"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["links"] == [{"url": "https://example.com/page", "start": 16, "end": 40}]
    assert body["content"][16:40] == "https://example.com/page"


async def test_javascript_and_data_schemes_are_never_returned_as_links(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "click javascript:alert(1) or data:text/html,<script>x</script>"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["links"] == []
    # Content itself is returned as plain text (no HTML), so a JSON string is
    # exactly what a client receives — nothing here is ever raw markup.
    assert isinstance(response.json()["content"], str)


# --- get + replies -------------------------------------------------------------


async def test_get_tweet_by_id(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    create_response = await async_client.post(
        "/api/v1/tweets", headers=headers, json={"content": "fetch me"}
    )
    tweet_id = create_response.json()["id"]

    get_response = await async_client.get(f"/api/v1/tweets/{tweet_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["content"] == "fetch me"


async def test_get_unknown_tweet_returns_404(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.get(f"/api/v1/tweets/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_reply_flow_increments_counter_and_notifies_and_lists(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)
    bob = await _register(async_client)
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    root_response = await async_client.post(
        "/api/v1/tweets", headers=alice_headers, json={"content": "root tweet"}
    )
    root_id = root_response.json()["id"]

    reply_response = await async_client.post(
        "/api/v1/tweets",
        headers=bob_headers,
        json={"content": "great point!", "parent_tweet_id": root_id},
    )
    assert reply_response.status_code == 201, reply_response.text
    reply_body = reply_response.json()
    assert reply_body["parent_tweet_id"] == root_id

    refreshed_root = await async_client.get(f"/api/v1/tweets/{root_id}", headers=alice_headers)
    assert refreshed_root.json()["reply_count"] == 1

    replies_response = await async_client.get(
        f"/api/v1/tweets/{root_id}/replies", headers=alice_headers
    )
    assert replies_response.status_code == 200
    replies_data = replies_response.json()["data"]
    assert len(replies_data) == 1
    assert replies_data[0]["content"] == "great point!"
    assert replies_data[0]["author"]["username"] == bob["username"]

    notifications_response = await async_client.get("/api/v1/notifications", headers=alice_headers)
    assert notifications_response.status_code == 200
    notif_body = notifications_response.json()
    assert notif_body["unread_count"] == 1
    assert notif_body["data"][0]["type"] == "reply"
    assert notif_body["data"][0]["actor"]["username"] == bob["username"]
    assert notif_body["data"][0]["tweet_id"] == root_id


async def test_cannot_reply_to_a_reply(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    bob = await _register(async_client)
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    bob_headers = await _auth_headers(async_client, email=bob["email"], password=bob["password"])

    root_response = await async_client.post(
        "/api/v1/tweets", headers=alice_headers, json={"content": "root"}
    )
    root_id = root_response.json()["id"]

    reply_response = await async_client.post(
        "/api/v1/tweets",
        headers=bob_headers,
        json={"content": "a reply", "parent_tweet_id": root_id},
    )
    reply_id = reply_response.json()["id"]

    nested_response = await async_client.post(
        "/api/v1/tweets",
        headers=alice_headers,
        json={"content": "nested reply", "parent_tweet_id": reply_id},
    )
    assert nested_response.status_code == 422, nested_response.text
    assert nested_response.json()["error"]["code"] == "semantic_validation_error"

    # And nothing was actually created: the reply's own replies list stays empty.
    replies_of_reply = await async_client.get(
        f"/api/v1/tweets/{reply_id}/replies", headers=alice_headers
    )
    assert replies_of_reply.json()["data"] == []


async def test_reply_to_missing_tweet_returns_404(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.post(
        "/api/v1/tweets",
        headers=headers,
        json={"content": "reply to nothing", "parent_tweet_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404, response.text


async def test_replies_paginate_oldest_first_without_duplicates(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])
    root_id = (
        await async_client.post("/api/v1/tweets", headers=headers, json={"content": "root"})
    ).json()["id"]

    for i in range(3):
        response = await async_client.post(
            "/api/v1/tweets",
            headers=headers,
            json={"content": f"reply-{i}", "parent_tweet_id": root_id},
        )
        assert response.status_code == 201

    page_1 = await async_client.get(
        f"/api/v1/tweets/{root_id}/replies", headers=headers, params={"limit": 2}
    )
    body_1 = page_1.json()
    assert [item["content"] for item in body_1["data"]] == ["reply-0", "reply-1"]
    assert body_1["page"]["next_cursor"] is not None

    page_2 = await async_client.get(
        f"/api/v1/tweets/{root_id}/replies",
        headers=headers,
        params={"limit": 2, "cursor": body_1["page"]["next_cursor"]},
    )
    body_2 = page_2.json()
    assert [item["content"] for item in body_2["data"]] == ["reply-2"]
    assert body_2["page"]["next_cursor"] is None

    malformed = await async_client.get(
        f"/api/v1/tweets/{root_id}/replies",
        headers=headers,
        params={"cursor": "not-a-valid-cursor"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "validation_error"


# --- profile timeline ----------------------------------------------------------


async def test_profile_timeline_returns_full_tweet_view(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    await async_client.post("/api/v1/tweets", headers=headers, json={"content": "timeline tweet"})

    response = await async_client.get(f"/api/v1/users/{alice['username']}/tweets", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["content"] == "timeline tweet"
    assert item["author"]["username"] == alice["username"]
    assert "liked_by_viewer" in item
    assert "media" in item
    assert "links" in item


async def test_profile_timeline_unknown_user_returns_404(async_client: AsyncClient) -> None:
    alice = await _register(async_client)
    headers = await _auth_headers(async_client, email=alice["email"], password=alice["password"])

    response = await async_client.get("/api/v1/users/no_such_user_at_all/tweets", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- rate limiting ---------------------------------------------------------------


async def test_tweet_create_rate_limit_returns_429_with_retry_after(
    async_client: AsyncClient,
) -> None:
    alice = await _register(async_client)

    limited_settings = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="tweets-ratelimit-secret",
        auth_rate_limit_per_minute=1000,
        tweet_rate_limit_per_minute=2,
    )
    limited_app = create_app(limited_settings)
    async with limited_app.router.lifespan_context(limited_app):
        transport = ASGITransport(app=limited_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = await _auth_headers(client, email=alice["email"], password=alice["password"])

            ok_1 = await client.post("/api/v1/tweets", headers=headers, json={"content": "one"})
            assert ok_1.status_code == 201
            ok_2 = await client.post("/api/v1/tweets", headers=headers, json={"content": "two"})
            assert ok_2.status_code == 201

            limited = await client.post(
                "/api/v1/tweets", headers=headers, json={"content": "three"}
            )
            assert limited.status_code == 429
            assert limited.json()["error"]["code"] == "rate_limited"
            assert "Retry-After" in limited.headers


# --- concurrency ------------------------------------------------------------------


async def test_concurrent_replies_to_the_same_tweet_all_land_correctly(
    async_client: AsyncClient,
) -> None:
    """A burst of concurrent `POST /tweets` replies to the same parent (each
    riding its own request-scoped DB session — a genuine concurrency race)
    all insert, the parent's `reply_count` ends up exactly matching the
    number of replies, and each generates exactly one notification.
    """
    alice = await _register(async_client)
    alice_headers = await _auth_headers(
        async_client, email=alice["email"], password=alice["password"]
    )
    root_response = await async_client.post(
        "/api/v1/tweets", headers=alice_headers, json={"content": "root for race"}
    )
    root_id = root_response.json()["id"]

    repliers = [await _register(async_client) for _ in range(5)]

    async def _reply(replier: dict[str, str], index: int) -> httpx.Response:
        headers = await _auth_headers(
            async_client, email=replier["email"], password=replier["password"]
        )
        return await async_client.post(
            "/api/v1/tweets",
            headers=headers,
            json={"content": f"race reply {index}", "parent_tweet_id": root_id},
        )

    responses = await asyncio.gather(*(_reply(replier, i) for i, replier in enumerate(repliers)))
    for response in responses:
        assert response.status_code == 201, response.text

    refreshed_root = await async_client.get(f"/api/v1/tweets/{root_id}", headers=alice_headers)
    assert refreshed_root.json()["reply_count"] == 5

    replies_response = await async_client.get(
        f"/api/v1/tweets/{root_id}/replies", headers=alice_headers, params={"limit": 50}
    )
    assert len(replies_response.json()["data"]) == 5

    notifications_response = await async_client.get("/api/v1/notifications", headers=alice_headers)
    assert notifications_response.json()["unread_count"] == 5
