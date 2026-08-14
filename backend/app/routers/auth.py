"""`/auth/*` endpoints (spec §6.3, §7.1): register, login, refresh, logout,
and the current-user lookup.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_current_user, get_db_session, get_redis, get_settings_dep
from app.core.rate_limit import check_rate_limit
from app.models.user import User
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.schemas.auth import AccessTokenResponse, LoginRequest, RegisterRequest, UserPublic
from app.services.auth import AuthService, InvalidRefreshTokenError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Best-effort caller IP for per-IP rate limiting. No `X-Forwarded-For`
    trust here (no reverse proxy in front of the app yet) -- revisit once
    `TSC-OPS-*` puts one in place.
    """
    if request.client is not None:
        return request.client.host
    return "unknown"


async def _enforce_auth_rate_limit(request: Request, redis: Redis, settings: Settings) -> None:
    """Per-IP sliding-window limit shared by every unauthenticated `/auth/*`
    endpoint (spec §10.3 default: "auth endpoints 10/min/IP").
    """
    await check_rate_limit(
        redis,
        key=f"auth:{_client_ip(request)}",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=60,
    )


def _auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    return AuthService(UserRepository(session), RefreshTokenRepository(session))


def _set_refresh_cookie(response: Response, raw_refresh_token: str, settings: Settings) -> None:
    """Set the refresh-token cookie: httpOnly + Secure (in non-local
    environments) + SameSite=Strict (spec §7.1, §10.2 CSRF rationale).
    """
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api/v1/auth",
    )


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account.",
)
async def register(
    request: Request,
    body: RegisterRequest,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    auth_service: AuthService = Depends(_auth_service),
) -> User:
    await _enforce_auth_rate_limit(request, redis, settings)
    return await auth_service.register(
        name=body.name, username=body.username, email=body.email, password=body.password
    )


@router.post(
    "/login",
    response_model=AccessTokenResponse,
    summary="Authenticate with email + password.",
)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    auth_service: AuthService = Depends(_auth_service),
) -> AccessTokenResponse:
    await _enforce_auth_rate_limit(request, redis, settings)
    user = await auth_service.authenticate(email=body.email, password=body.password)
    session = await auth_service.issue_session(user, settings)
    _set_refresh_cookie(response, session.refresh_token, settings)
    return AccessTokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Rotate the refresh cookie for a new access token.",
)
async def refresh(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    auth_service: AuthService = Depends(_auth_service),
) -> AccessTokenResponse:
    await _enforce_auth_rate_limit(request, redis, settings)
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_refresh_token:
        raise InvalidRefreshTokenError()

    _, session = await auth_service.rotate_refresh_token(raw_refresh_token, settings)
    _set_refresh_cookie(response, session.refresh_token, settings)
    return AccessTokenResponse(access_token=session.access_token, expires_in=session.expires_in)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the refresh token and clear the cookie.",
)
async def logout(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings_dep),
    auth_service: AuthService = Depends(_auth_service),
) -> None:
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh_token:
        await auth_service.logout(raw_refresh_token, settings)
    _clear_refresh_cookie(response, settings)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get the authenticated user.",
)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
