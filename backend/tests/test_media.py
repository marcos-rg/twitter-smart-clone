"""Integration tests for the media upload backend (TSC-MEDIA-001, spec
§8.4) against real PostgreSQL *and* real MinIO: presign, an actual direct
`PUT` to the presigned URL (never through the API), and confirm.

Mirrors `tests/test_users.py`'s app/async_client fixture setup (real
Postgres via `ASGITransport`, no mocking of the DB layer). Unlike that
file, several tests here also make a *second*, non-ASGI `httpx.AsyncClient`
call straight to the presigned URL — that's the point: the upload itself
must never go through the FastAPI app.
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

# A few bytes each — MinIO stores whatever bytes it's given regardless of
# whether they form a "real" decodable image; what matters for these tests
# is the declared vs. actual content-type/length, not decodability.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 100
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"1" * 100
WEBP_BYTES = b"RIFF" + b"2" * 100 + b"WEBPVP8 "


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_media() -> None:
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
        # `users CASCADE` also empties `pending_uploads` (FK -> users.id).
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, "
                "tweet_media, tweets, pending_uploads, users CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
def media_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="media-test-secret",
        auth_rate_limit_per_minute=1000,
    )


@pytest.fixture
def short_expiry_settings() -> Settings:
    """A presigned URL that expires almost immediately, for the expiry test."""
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="media-test-secret",
        auth_rate_limit_per_minute=1000,
        media_presign_expires_seconds=1,
    )


@pytest_asyncio.fixture
async def app(media_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_tables()
    application = create_app(media_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def short_expiry_app(short_expiry_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_tables()
    application = create_app(short_expiry_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def short_expiry_client(short_expiry_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=short_expiry_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _register(client: AsyncClient, **overrides: str) -> dict[str, str]:
    suffix = _unique_suffix()
    payload = {
        "name": "Media Uploader",
        "username": f"media{suffix}",
        "email": f"media{suffix}@example.com",
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
    """Upload straight to the presigned URL — never through the FastAPI app."""
    async with httpx.AsyncClient() as raw_client:
        return await raw_client.put(
            upload_url, content=body, headers={"Content-Type": content_type}
        )


# --- presign + upload + confirm round trip ------------------------------------


@pytest.mark.parametrize(
    ("content_type", "body"),
    [("image/png", PNG_BYTES), ("image/jpeg", JPEG_BYTES), ("image/webp", WEBP_BYTES)],
    ids=["png", "jpeg", "webp"],
)
async def test_presign_upload_confirm_tweet_image_round_trip(
    async_client: AsyncClient, content_type: str, body: bytes
) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    presign = await async_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "tweet_image",
            "files": [{"content_type": content_type, "size_bytes": len(body)}],
        },
    )
    assert presign.status_code == 200, presign.text
    upload = presign.json()["uploads"][0]

    # The presigned URL points directly at MinIO, not at this API — the
    # API process never sees the image bytes in either request.
    assert urlparse(upload["upload_url"]).hostname == "minio"

    put_response = await _put_object(upload["upload_url"], body=body, content_type=content_type)
    assert put_response.status_code in (200, 201), put_response.text

    confirm = await async_client.post(
        "/api/v1/media/confirm",
        headers=headers,
        json={"purpose": "tweet_image", "keys": [upload["key"]]},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["media"] == [
        {"key": upload["key"], "content_type": content_type, "size_bytes": len(body)}
    ]


async def test_confirm_avatar_updates_profile_and_survives_fresh_read(
    async_client: AsyncClient,
) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    presign = await async_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "avatar",
            "files": [{"content_type": "image/png", "size_bytes": len(PNG_BYTES)}],
        },
    )
    upload = presign.json()["uploads"][0]
    put_response = await _put_object(upload["upload_url"], body=PNG_BYTES, content_type="image/png")
    assert put_response.status_code in (200, 201), put_response.text

    confirm = await async_client.post(
        "/api/v1/users/me/avatar", headers=headers, json={"key": upload["key"]}
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["avatar_key"] == upload["key"]

    # Fresh, independent read (own profile + public profile) both show it.
    me = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    profile = await async_client.get(f"/api/v1/users/{user['username']}", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["avatar_key"] == upload["key"]


async def test_api_request_bodies_never_carry_image_bytes(async_client: AsyncClient) -> None:
    """Presign and confirm request bodies are small JSON documents
    regardless of the (declared) image size — proof the API never expects
    or proxies raw image bytes during the normal upload flow.
    """
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    declared_size = 4 * 1024 * 1024  # 4MB declared, but no bytes are ever sent to the API.
    presign_body = {
        "purpose": "avatar",
        "files": [{"content_type": "image/png", "size_bytes": declared_size}],
    }
    presign_request = async_client.build_request("POST", "/api/v1/media/presign", json=presign_body)
    assert presign_request.content is not None
    assert len(presign_request.content) < 1024  # tiny JSON body, not 4MB of pixels

    presign = await async_client.post("/api/v1/media/presign", headers=headers, json=presign_body)
    assert presign.status_code == 200
    upload = presign.json()["uploads"][0]

    confirm_body = {"key": upload["key"]}
    confirm_request = async_client.build_request(
        "POST", "/api/v1/users/me/avatar", json=confirm_body
    )
    assert confirm_request.content is not None
    assert len(confirm_request.content) < 1024


# --- rejections ------------------------------------------------------------------


async def test_presign_rejects_unsupported_content_type(async_client: AsyncClient) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    response = await async_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "tweet_image",
            "files": [{"content_type": "image/gif", "size_bytes": 1024}],
        },
    )
    assert response.status_code == 400, response.text


async def test_presign_rejects_oversized_file(async_client: AsyncClient) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    response = await async_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "tweet_image",
            "files": [{"content_type": "image/png", "size_bytes": 10 * 1024 * 1024}],
        },
    )
    assert response.status_code == 400, response.text


async def test_presign_rejects_more_than_four_tweet_images(async_client: AsyncClient) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    files = [{"content_type": "image/png", "size_bytes": 1024} for _ in range(5)]
    response = await async_client.post(
        "/api/v1/media/presign", headers=headers, json={"purpose": "tweet_image", "files": files}
    )
    assert response.status_code == 400, response.text


async def test_confirm_rejects_object_that_was_never_uploaded(async_client: AsyncClient) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    presign = await async_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "avatar",
            "files": [{"content_type": "image/png", "size_bytes": len(PNG_BYTES)}],
        },
    )
    upload = presign.json()["uploads"][0]

    # Never uploaded to `upload["upload_url"]`.
    confirm = await async_client.post(
        "/api/v1/users/me/avatar", headers=headers, json={"key": upload["key"]}
    )
    assert confirm.status_code == 400, confirm.text


async def test_confirm_rejects_altered_metadata(async_client: AsyncClient) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    presign = await async_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "avatar",
            "files": [{"content_type": "image/png", "size_bytes": len(JPEG_BYTES)}],
        },
    )
    upload = presign.json()["uploads"][0]

    # Uploads a *different* file (JPEG bytes, JPEG content-type) than
    # declared (PNG) at presign time. MinIO signs on `ContentType`, so this
    # PUT itself is rejected by MinIO — that's the first line of defense.
    put_response = await _put_object(
        upload["upload_url"], body=JPEG_BYTES, content_type="image/jpeg"
    )
    assert put_response.status_code >= 400

    confirm = await async_client.post(
        "/api/v1/users/me/avatar", headers=headers, json={"key": upload["key"]}
    )
    assert confirm.status_code == 400, confirm.text


async def test_confirm_rejects_key_owned_by_another_user(async_client: AsyncClient) -> None:
    owner = await _register(async_client)
    owner_headers = await _auth_headers(
        async_client, email=owner["email"], password=owner["password"]
    )
    other = await _register(async_client)
    other_headers = await _auth_headers(
        async_client, email=other["email"], password=other["password"]
    )

    presign = await async_client.post(
        "/api/v1/media/presign",
        headers=owner_headers,
        json={
            "purpose": "avatar",
            "files": [{"content_type": "image/png", "size_bytes": len(PNG_BYTES)}],
        },
    )
    upload = presign.json()["uploads"][0]
    put_response = await _put_object(upload["upload_url"], body=PNG_BYTES, content_type="image/png")
    assert put_response.status_code in (200, 201)

    confirm = await async_client.post(
        "/api/v1/users/me/avatar", headers=other_headers, json={"key": upload["key"]}
    )
    assert confirm.status_code == 403, confirm.text


async def test_confirm_rejects_unknown_key(async_client: AsyncClient) -> None:
    user = await _register(async_client)
    headers = await _auth_headers(async_client, email=user["email"], password=user["password"])

    response = await async_client.post(
        "/api/v1/users/me/avatar",
        headers=headers,
        json={"key": "avatar/does-not-exist/nope.png"},
    )
    assert response.status_code == 404, response.text


# --- expiry ------------------------------------------------------------------


async def test_presigned_url_expires(short_expiry_client: AsyncClient) -> None:
    user = await _register(short_expiry_client)
    headers = await _auth_headers(
        short_expiry_client, email=user["email"], password=user["password"]
    )

    presign = await short_expiry_client.post(
        "/api/v1/media/presign",
        headers=headers,
        json={
            "purpose": "avatar",
            "files": [{"content_type": "image/png", "size_bytes": len(PNG_BYTES)}],
        },
    )
    upload = presign.json()["uploads"][0]

    await asyncio.sleep(2)  # let the 1-second-expiry URL expire

    put_response = await _put_object(upload["upload_url"], body=PNG_BYTES, content_type="image/png")
    assert put_response.status_code >= 400, "expired presigned URL should be rejected by MinIO"
