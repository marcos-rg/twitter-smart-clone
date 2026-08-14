"""`/users/{username}/follow`, `/followers`, `/following` routes (spec
§6.1, §6.3 "Follows").
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_current_user, get_db_session, get_redis, get_settings_dep
from app.core.rate_limit import check_rate_limit
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRepository
from app.schemas.follows import FollowListResponse, FollowRelationship, FollowUserItem
from app.schemas.users import PageInfo
from app.services.follows import FollowsService
from app.services.notifications import NotificationsService

router = APIRouter(prefix="/api/v1/users", tags=["follows"])


def _follows_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> FollowsService:
    notifications_service = NotificationsService(
        NotificationRepository(session), UserRepository(session), session, redis
    )
    return FollowsService(FollowRepository(session), UserRepository(session), notifications_service)


async def _enforce_follow_rate_limit(current_user: User, redis: Redis, settings: Settings) -> None:
    """Per-user sliding-window limit shared by follow and unfollow (spec
    §10.3 suggested default: "likes/follows 60/min/user").
    """
    await check_rate_limit(
        redis,
        key=f"follow:{current_user.id}",
        limit=settings.follow_rate_limit_per_minute,
        window_seconds=60,
    )


@router.post(
    "/{username}/follow",
    response_model=FollowRelationship,
    summary="Follow a user (idempotent).",
)
async def follow_user(
    username: str,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    current_user: User = Depends(get_current_user),
    service: FollowsService = Depends(_follows_service),
) -> FollowRelationship:
    await _enforce_follow_rate_limit(current_user, redis, settings)
    result = await service.follow(current_user, username)
    return FollowRelationship(
        following=result.is_following, followers_count=result.followers_count
    )


@router.delete(
    "/{username}/follow",
    response_model=FollowRelationship,
    summary="Unfollow a user (idempotent).",
)
async def unfollow_user(
    username: str,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    current_user: User = Depends(get_current_user),
    service: FollowsService = Depends(_follows_service),
) -> FollowRelationship:
    await _enforce_follow_rate_limit(current_user, redis, settings)
    result = await service.unfollow(current_user, username)
    return FollowRelationship(
        following=result.is_following, followers_count=result.followers_count
    )


@router.get(
    "/{username}/followers",
    response_model=FollowListResponse,
    summary="List a user's followers (paginated).",
)
async def list_followers(
    username: str,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    _: User = Depends(get_current_user),
    service: FollowsService = Depends(_follows_service),
) -> FollowListResponse:
    page = await service.list_followers(username, cursor=cursor, limit=limit)
    return FollowListResponse(
        data=[FollowUserItem.model_validate(user) for user in page.items],
        page=PageInfo(next_cursor=page.next_cursor),
    )


@router.get(
    "/{username}/following",
    response_model=FollowListResponse,
    summary="List who a user follows (paginated).",
)
async def list_following(
    username: str,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    _: User = Depends(get_current_user),
    service: FollowsService = Depends(_follows_service),
) -> FollowListResponse:
    page = await service.list_following(username, cursor=cursor, limit=limit)
    return FollowListResponse(
        data=[FollowUserItem.model_validate(user) for user in page.items],
        page=PageInfo(next_cursor=page.next_cursor),
    )
