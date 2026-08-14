"""Unit/integration tests for `AuthService` (`TSC-AUTH-001`, spec §7.1)
against a real PostgreSQL session (`tests/services/conftest.py`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.security import hash_refresh_token
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.services.auth import (
    AuthService,
    DuplicateAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret_key="service-test-secret", environment="test")


@pytest.fixture
def auth_service(db_session: AsyncSession) -> AuthService:
    return AuthService(UserRepository(db_session), RefreshTokenRepository(db_session))


async def test_register_creates_a_user_with_a_hashed_password(auth_service: AuthService) -> None:
    user = await auth_service.register(
        name="Ada Lovelace", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    assert user.id is not None
    assert user.username == "ada"
    assert user.password_hash != "s3cret-pass!"


async def test_register_rejects_duplicate_username(auth_service: AuthService) -> None:
    await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    with pytest.raises(DuplicateAccountError):
        await auth_service.register(
            name="Someone Else",
            username="ada",
            email="different@example.com",
            password="s3cret-pass!",
        )


async def test_register_rejects_duplicate_email(auth_service: AuthService) -> None:
    await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    with pytest.raises(DuplicateAccountError):
        await auth_service.register(
            name="Someone Else",
            username="someoneelse",
            email="ada@example.com",
            password="s3cret-pass!",
        )


async def test_authenticate_succeeds_with_correct_credentials(auth_service: AuthService) -> None:
    await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    user = await auth_service.authenticate(email="ada@example.com", password="s3cret-pass!")
    assert user.username == "ada"


async def test_authenticate_rejects_wrong_password(auth_service: AuthService) -> None:
    await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    with pytest.raises(InvalidCredentialsError):
        await auth_service.authenticate(email="ada@example.com", password="wrong-password")


async def test_authenticate_rejects_unknown_email_with_the_same_error(
    auth_service: AuthService,
) -> None:
    """Non-enumerating: an unknown email raises the exact same error/message
    as a wrong password for a real account (spec: "standard, non-enumerating
    errors").
    """
    with pytest.raises(InvalidCredentialsError) as exc_info:
        await auth_service.authenticate(email="nobody@example.com", password="whatever")
    assert exc_info.value.message == "Invalid email or password."
    assert exc_info.value.status_code == 401


async def test_issue_session_persists_only_the_refresh_token_hash(
    auth_service: AuthService, settings: Settings
) -> None:
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    session = await auth_service.issue_session(user, settings)

    stored = await auth_service.refresh_tokens.get_by_token_hash(
        hash_refresh_token(session.refresh_token, settings)
    )
    assert stored is not None
    assert stored.token_hash != session.refresh_token


async def test_rotate_refresh_token_issues_a_new_token_and_revokes_the_old_one(
    auth_service: AuthService, settings: Settings
) -> None:
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    first_session = await auth_service.issue_session(user, settings)

    rotated_user, second_session = await auth_service.rotate_refresh_token(
        first_session.refresh_token, settings
    )

    assert rotated_user.id == user.id
    assert second_session.refresh_token != first_session.refresh_token

    # The old (rotated-away) token can no longer be used to authenticate.
    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token(first_session.refresh_token, settings)


async def test_reused_refresh_token_revokes_the_entire_family(
    auth_service: AuthService, settings: Settings
) -> None:
    """Concurrency/replay case: once a refresh token has been rotated, a
    later replay of that same (now-stale) token must not just fail -- it must
    revoke every other still-active token for that user too (spec: "reuse
    detection ⇒ revoke the whole family"), so a stolen-and-replayed token
    can't be used even via a token that *was* validly rotated in between.
    """
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    first_session = await auth_service.issue_session(user, settings)
    _, second_session = await auth_service.rotate_refresh_token(
        first_session.refresh_token, settings
    )

    # Replay the original (already-rotated) token: reuse detected.
    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token(first_session.refresh_token, settings)

    # The entire family -- including the token issued by the *legitimate*
    # rotation above -- must now be revoked too.
    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token(second_session.refresh_token, settings)


async def test_rotate_refresh_token_rejects_unknown_token(
    auth_service: AuthService, settings: Settings
) -> None:
    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token("not-a-real-refresh-token", settings)


async def test_rotate_refresh_token_rejects_an_expired_but_unrevoked_token(
    auth_service: AuthService, settings: Settings
) -> None:
    """A token past its `expires_at` (but never explicitly revoked, e.g. an
    old cookie the client never used again) must still be rejected -- expiry
    is checked independently of the revocation flag.
    """
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="correct horse battery staple"
    )
    session = await auth_service.issue_session(user, settings)

    token = await auth_service.refresh_tokens.get_by_token_hash(
        hash_refresh_token(session.refresh_token, settings)
    )
    assert token is not None
    token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_service.refresh_tokens.session.flush()

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token(session.refresh_token, settings)


async def test_rotate_refresh_token_rejects_a_token_for_a_deleted_user(
    auth_service: AuthService, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A structurally-valid, still-active refresh token whose user account
    no longer exists (e.g. deleted through some future cascading admin path)
    is rejected with the same generic error as any other invalid token --
    never a different message/status that would leak whether the account
    ever existed. The `users` table's FK from `refresh_tokens` makes this
    unreachable via the repositories alone today, so the "user vanished"
    branch is exercised here by monkeypatching the user lookup.
    """
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="correct horse battery staple"
    )
    session = await auth_service.issue_session(user, settings)
    monkeypatch.setattr(auth_service.users, "get", AsyncMock(return_value=None))

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token(session.refresh_token, settings)


async def test_get_user_returns_the_user_by_id(auth_service: AuthService) -> None:
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="correct horse battery staple"
    )

    fetched = await auth_service.get_user(user.id)

    assert fetched is not None
    assert fetched.id == user.id


async def test_get_user_returns_none_for_an_unknown_id(auth_service: AuthService) -> None:
    assert await auth_service.get_user(uuid.uuid4()) is None


async def test_logout_revokes_the_refresh_token(
    auth_service: AuthService, settings: Settings
) -> None:
    user = await auth_service.register(
        name="Ada", username="ada", email="ada@example.com", password="s3cret-pass!"
    )
    session = await auth_service.issue_session(user, settings)

    await auth_service.logout(session.refresh_token, settings)

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.rotate_refresh_token(session.refresh_token, settings)


async def test_logout_is_idempotent_for_an_unknown_token(
    auth_service: AuthService, settings: Settings
) -> None:
    """Logout never errors even for a token that doesn't exist (already
    logged out / stale cookie) -- it always "succeeds" from the client's
    perspective.
    """
    await auth_service.logout("not-a-real-refresh-token", settings)
