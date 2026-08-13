"""Integration tests for `/api/v1/auth/*` (`TSC-AUTH-001`, spec §6.3, §7.1):
the full request/response contract, cookie attributes, non-enumerating
errors, refresh rotation/reuse, and rate limiting.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app

pytestmark = pytest.mark.asyncio

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


async def _truncate_auth_tables() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE refresh_tokens, users CASCADE"))
    await engine.dispose()


@pytest.fixture
def auth_settings() -> Settings:
    """A high rate limit by default: most tests don't exercise rate limiting
    and shouldn't be flaky if run alongside others hitting the same in-memory
    Redis. Tests that *do* care about rate limiting override this per-test.
    """
    return Settings(
        environment="test",
        jwt_secret_key="router-test-secret",
        auth_rate_limit_per_minute=1000,
    )


@pytest_asyncio.fixture
async def app(auth_settings: Settings) -> AsyncIterator[FastAPI]:
    await _truncate_auth_tables()
    application = create_app(auth_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An `httpx.AsyncClient` against the app over an in-process ASGI
    transport (no real socket), so its cookie jar tracks the refresh cookie
    exactly like a real browser across `/auth/login` -> `/auth/refresh` ->
    `/auth/logout`.
    """
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


# --- Register ----------------------------------------------------------------


async def test_register_returns_public_user_shape_without_password(
    async_client: AsyncClient,
) -> None:
    payload = await _register(async_client)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    data = response.json()["user"]
    assert data["username"] == payload["username"]
    assert data["email"] == payload["email"]
    assert "password" not in data
    assert "password_hash" not in data


async def test_register_rejects_duplicate_email(async_client: AsyncClient) -> None:
    payload = await _register(async_client)
    suffix = _unique_suffix()
    response = await async_client.post(
        "/api/v1/auth/register",
        json={**payload, "username": f"other{suffix}"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_register_rejects_duplicate_username(async_client: AsyncClient) -> None:
    payload = await _register(async_client)
    suffix = _unique_suffix()
    response = await async_client.post(
        "/api/v1/auth/register",
        json={**payload, "email": f"other{suffix}@example.com"},
    )
    assert response.status_code == 409


async def test_register_validates_request_body(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"name": "", "username": "x", "email": "not-an-email", "password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "semantic_validation_error"


# --- Login ---------------------------------------------------------------------


async def test_login_returns_access_token_and_sets_refresh_cookie(
    async_client: AsyncClient,
) -> None:
    payload = await _register(async_client)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == payload["email"]
    assert "password" not in body["user"]

    set_cookie = response.headers["set-cookie"]
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    assert "Path=/api/v1/auth" in set_cookie
    # Not `Secure` in a non-production environment (spec: "secure cookie
    # configuration by environment") -- a plain-HTTP local/test origin would
    # never actually send a `Secure` cookie back anyway.
    assert "Secure" not in set_cookie


async def test_login_sets_a_secure_cookie_in_production(auth_settings: Settings) -> None:
    prod_settings = auth_settings.model_copy(update={"environment": "production"})
    await _truncate_auth_tables()

    application = create_app(prod_settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = await _register(ac)
            response = await ac.post(
                "/api/v1/auth/login",
                json={"email": payload["email"], "password": payload["password"]},
            )
            assert response.status_code == 200
            assert "Secure" in response.headers["set-cookie"]


async def test_login_rejects_wrong_password_with_generic_message(
    async_client: AsyncClient,
) -> None:
    payload = await _register(async_client)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "totally-wrong"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


async def test_login_rejects_unknown_email_with_the_same_generic_message(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody-at-all@example.com", "password": "whatever12345"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."
    assert response.json()["error"]["code"] == "unauthenticated"


# --- /auth/me ---------------------------------------------------------------------


async def test_me_requires_a_bearer_token(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_a_malformed_token(async_client: AsyncClient) -> None:
    response = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401


async def test_me_returns_the_authenticated_user(async_client: AsyncClient) -> None:
    payload = await _register(async_client)
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    access_token = login_response.json()["access_token"]

    response = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == payload["email"]


async def test_me_rejects_a_well_formed_token_for_a_nonexistent_user(
    async_client: AsyncClient, auth_settings: Settings
) -> None:
    """A structurally-valid, correctly-signed access token whose subject
    doesn't match any user (e.g. the account was deleted after the token was
    issued) is rejected with the same generic `401` as any other invalid
    token -- never a `404`/different message that would leak account state.
    """
    token, _ = create_access_token(uuid.uuid4(), auth_settings)
    response = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# --- Refresh rotation + reuse detection -----------------------------------------


async def test_refresh_without_a_cookie_is_unauthenticated(async_client: AsyncClient) -> None:
    response = await async_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


async def test_refresh_rotates_the_cookie_and_issues_a_new_access_token(
    async_client: AsyncClient,
) -> None:
    payload = await _register(async_client)
    await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    old_cookie = async_client.cookies.get("refresh_token")

    refresh_response = await async_client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]
    assert refresh_response.json()["user"] is None

    # The opaque refresh token is rotated to a brand-new value (the JWT
    # access token, in contrast, may legitimately be byte-identical to the
    # previous one if reissued within the same second -- its claims are
    # `(sub, type, iat, exp)` at second precision, so that alone isn't a
    # useful "did rotation happen?" signal; the refresh cookie is).
    new_cookie = async_client.cookies.get("refresh_token")
    assert new_cookie != old_cookie


async def test_replayed_refresh_token_revokes_the_whole_family(
    async_client: AsyncClient,
) -> None:
    """Concurrency/replay: exchange the refresh cookie once (a valid
    rotation), then replay the *original* cookie (simulating a stolen/
    duplicated token) -- both that replay and any further use of the
    legitimately-rotated cookie must now be rejected.
    """
    payload = await _register(async_client)
    await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    original_cookie = async_client.cookies.get("refresh_token")

    first_refresh = await async_client.post("/api/v1/auth/refresh")
    assert first_refresh.status_code == 200
    rotated_cookie = async_client.cookies.get("refresh_token")
    assert rotated_cookie != original_cookie

    # Replay the stale, already-rotated-away original cookie. Sent via an
    # explicit `Cookie` header (bypassing the client's persistent cookie
    # jar, which would otherwise keep merging/overwriting by name) so this
    # single request unambiguously presents the *old* value.
    replay_response = await async_client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={original_cookie}"}
    )
    assert replay_response.status_code == 401

    # The legitimately-rotated cookie must be revoked too (whole-family
    # revocation), even though it was never itself replayed. The client's
    # cookie jar still holds it (the header-based replay request above never
    # touched the jar), so a normal request reuses it automatically.
    assert async_client.cookies.get("refresh_token") == rotated_cookie
    second_attempt = await async_client.post("/api/v1/auth/refresh")
    assert second_attempt.status_code == 401


# --- Logout ------------------------------------------------------------------------


async def test_logout_clears_the_cookie_and_revokes_the_session(
    async_client: AsyncClient,
) -> None:
    payload = await _register(async_client)
    await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )

    logout_response = await async_client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204
    set_cookie = logout_response.headers["set-cookie"]
    assert "refresh_token=" in set_cookie
    assert "max-age=0" in set_cookie.lower()

    refresh_response = await async_client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


async def test_logout_without_a_cookie_still_returns_204(async_client: AsyncClient) -> None:
    response = await async_client.post("/api/v1/auth/logout")
    assert response.status_code == 204


# --- Rate limiting --------------------------------------------------------------


async def test_login_is_rate_limited_per_ip(auth_settings: Settings) -> None:
    limited_settings = auth_settings.model_copy(update={"auth_rate_limit_per_minute": 3})
    await _truncate_auth_tables()

    application = create_app(limited_settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # This app instance's own Redis client, flushed so no counter
            # from another test in the same run affects this one (rate-limit
            # keys are scoped by caller IP, which is fixed for in-process
            # ASGI test transports).
            resources = application.state.resources
            redis: Redis = resources.redis
            await redis.flushdb()

            statuses = []
            for _ in range(5):
                response = await ac.post(
                    "/api/v1/auth/login",
                    json={"email": "nobody@example.com", "password": "whatever12345"},
                )
                statuses.append(response.status_code)

            assert statuses[:3] == [401, 401, 401]
            assert statuses[3:] == [429, 429]

            last_response = await ac.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "whatever12345"},
            )
            assert last_response.status_code == 429
            assert "retry-after" in {k.lower() for k in last_response.headers}
            assert last_response.json()["error"]["code"] == "rate_limited"
