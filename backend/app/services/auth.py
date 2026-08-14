"""Business logic for `/auth/*` (spec §7.1): register, authenticate, and
rotating-refresh-token session management.

Kept deliberately framework-agnostic (no `Request`/`Response`/cookies here --
`app.routers.auth` owns the HTTP boundary) so it's directly unit-testable
against a real `AsyncSession`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository

#: Generic, non-enumerating message for any login/refresh failure -- never
#: reveals whether the email exists, the password was wrong, or the token
#: was invalid/expired/revoked (spec: "standard, non-enumerating errors").
_INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."
_INVALID_REFRESH_MESSAGE = "Invalid or expired session. Please log in again."


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "unauthenticated"

    def __init__(self, message: str = _INVALID_CREDENTIALS_MESSAGE) -> None:
        super().__init__(message)


class InvalidRefreshTokenError(AppError):
    status_code = 401
    code = "unauthenticated"

    def __init__(self, message: str = _INVALID_REFRESH_MESSAGE) -> None:
        super().__init__(message)


class DuplicateAccountError(AppError):
    status_code = 409
    code = "conflict"


@dataclass
class IssuedSession:
    """The pair a caller needs to establish a session: a JWT access token
    (returned in the response body) and a raw refresh token (set as the
    httpOnly cookie -- never returned in a JSON body).
    """

    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    """Registration, login, refresh-rotation, and logout for email/password
    accounts (spec §7.1). Reused verbatim by the WebSocket auth path
    (`TSC-CORE-*`/`TSC-NOTIF-*`) via `decode_access_token` in `core.security`.
    """

    def __init__(self, users: UserRepository, refresh_tokens: RefreshTokenRepository) -> None:
        self.users = users
        self.refresh_tokens = refresh_tokens

    async def register(self, *, name: str, username: str, email: str, password: str) -> User:
        """Create a new account. Raises `DuplicateAccountError` (`409`) if the
        username or email is already taken (case-insensitively, via the
        `citext` columns) -- safe to reveal here since this is the caller's
        own registration attempt, not a login/enumeration surface.
        """
        if await self.users.get_by_username(username) is not None:
            raise DuplicateAccountError("Username is already taken.")
        if await self.users.get_by_email(email) is not None:
            raise DuplicateAccountError("Email is already registered.")

        user = User(
            name=name,
            username=username,
            email=email,
            password_hash=hash_password(password),
        )
        return await self.users.add(user)

    async def authenticate(self, *, email: str, password: str) -> User:
        """Verify email/password credentials, raising the same generic
        `InvalidCredentialsError` whether the account doesn't exist or the
        password is wrong (no user enumeration).
        """
        user = await self.users.get_by_email(email)
        if user is None:
            dummy_hash = globals().get("_DUMMY_PASSWORD_HASH")
            if dummy_hash is None:
                dummy_hash = globals()["_DUMMY_PASSWORD_HASH"] = hash_password(
                    "dummy-timing-safety-password"
                )
            verify_password(password, dummy_hash)
            raise InvalidCredentialsError()
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        return user

    async def issue_session(self, user: User, settings: Settings) -> IssuedSession:
        """Mint a fresh access token + refresh token pair for `user`,
        persisting only the refresh token's hash.
        """
        access_token, expires_in = create_access_token(user.id, settings)
        raw_refresh_token = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expires_days)
        token = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh_token, settings),
            expires_at=expires_at,
        )
        await self.refresh_tokens.add(token)
        return IssuedSession(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=raw_refresh_token,
            refresh_expires_at=expires_at,
        )

    async def rotate_refresh_token(
        self, raw_refresh_token: str, settings: Settings
    ) -> tuple[User, IssuedSession]:
        """Exchange a valid refresh token for a new access + refresh token
        pair, revoking the old one (spec: "every `/auth/refresh` issues a new
        refresh token and revokes the old one").

        Reuse detection: if the presented token has *already* been revoked
        (i.e. it was legitimately rotated before, or stolen and now replayed)
        the entire token family for that user is revoked, forcing re-login
        everywhere (spec: "reuse detection ⇒ revoke the whole family").
        """
        token_hash = hash_refresh_token(raw_refresh_token, settings)
        token = await self.refresh_tokens.get_by_token_hash(token_hash)
        if token is None:
            raise InvalidRefreshTokenError()

        if token.revoked_at is not None:
            await self.refresh_tokens.revoke_all_for_user(token.user_id)
            raise InvalidRefreshTokenError()

        if not self.refresh_tokens.is_active(token):
            raise InvalidRefreshTokenError()

        user = await self.users.get(token.user_id)
        if user is None:
            raise InvalidRefreshTokenError()

        await self.refresh_tokens.revoke(token)
        session = await self.issue_session(user, settings)
        return user, session

    async def logout(self, raw_refresh_token: str, settings: Settings) -> None:
        """Revoke the presented refresh token. Idempotent/silent if the token
        is unknown or already revoked -- logout always "succeeds" from the
        client's perspective.
        """
        token_hash = hash_refresh_token(raw_refresh_token, settings)
        token = await self.refresh_tokens.get_by_token_hash(token_hash)
        if token is not None and token.revoked_at is None:
            await self.refresh_tokens.revoke(token)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.users.get(user_id)
