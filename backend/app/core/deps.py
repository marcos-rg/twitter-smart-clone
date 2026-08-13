"""Shared FastAPI dependencies: request-scoped DB session, resource access,
and access-token authentication (spec §7.2: "a FastAPI dependency validates
the access token and injects the current user; protected routers depend on
it").
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.resources import AppResources
from app.core.security import InvalidTokenError, decode_access_token
from app.models.user import User
from app.repositories.users import UserRepository

#: `auto_error=False` so a missing/malformed `Authorization` header raises
#: our own standard error envelope (via `get_current_user`) instead of
#: FastAPI's default `403` `HTTPBearer` response.
_bearer_scheme = HTTPBearer(auto_error=False)


class UnauthenticatedError(AppError):
    """Standard, non-enumerating `401` for any authentication failure."""

    status_code = 401
    code = "unauthenticated"

    def __init__(self, message: str = "Authentication is required.") -> None:
        super().__init__(message)


def get_settings_dep(request: Request) -> Settings:
    """The `Settings` instance the running app was built with."""
    settings: Settings = request.app.state.settings
    return settings


def get_resources(request: Request) -> AppResources:
    """The process-wide async resource handles (DB/Redis/S3)."""
    resources: AppResources = request.app.state.resources
    return resources


async def get_db_session(
    resources: AppResources = Depends(get_resources),
) -> AsyncIterator[AsyncSession]:
    """A request-scoped `AsyncSession`, committed on success and rolled back
    on any exception so a failed request never leaves a partial write.
    """
    async with resources.db_sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(resources: AppResources = Depends(get_resources)) -> Redis:
    """The shared async Redis client (rate limiting, cache, pub/sub)."""
    return resources.redis


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings_dep),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Validate the `Bearer` access token and load the authenticated `User`.

    Raises the standard `401` envelope for a missing header, an invalid/
    expired token, or a token referencing a user that no longer exists —
    deliberately the same generic message in every case (spec: "standard,
    non-enumerating errors").
    """
    if credentials is None:
        raise UnauthenticatedError()
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as exc:
        raise UnauthenticatedError() from exc

    user = await UserRepository(session).get(user_id)
    if user is None:
        raise UnauthenticatedError()

    request.state.user_id = str(user.id)
    return user
