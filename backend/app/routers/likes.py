"""`/tweets/{id}/like` routes (spec §6.1, §6.3 "Likes")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_current_user, get_db_session, get_redis, get_settings_dep
from app.core.rate_limit import check_rate_limit
from app.models.user import User
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.schemas.likes import LikeRelationship
from app.services.likes import LikesService
from app.services.notifications import NotificationsService

router = APIRouter(prefix="/api/v1/tweets", tags=["likes"])


def _likes_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> LikesService:
    notifications_service = NotificationsService(
        NotificationRepository(session), UserRepository(session), session, redis
    )
    return LikesService(LikeRepository(session), TweetRepository(session), notifications_service)


async def _enforce_like_rate_limit(current_user: User, redis: Redis, settings: Settings) -> None:
    """Per-user sliding-window limit shared by like and unlike (spec §10.3
    suggested default: "likes/follows 60/min/user").
    """
    await check_rate_limit(
        redis,
        key=f"like:{current_user.id}",
        limit=settings.like_rate_limit_per_minute,
        window_seconds=60,
    )


@router.post(
    "/{tweet_id}/like",
    response_model=LikeRelationship,
    summary="Like a tweet (idempotent).",
)
async def like_tweet(
    tweet_id: UUID,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    current_user: User = Depends(get_current_user),
    service: LikesService = Depends(_likes_service),
) -> LikeRelationship:
    await _enforce_like_rate_limit(current_user, redis, settings)
    result = await service.like(current_user, tweet_id)
    return LikeRelationship(liked=result.liked, like_count=result.like_count)


@router.delete(
    "/{tweet_id}/like",
    response_model=LikeRelationship,
    summary="Unlike a tweet (idempotent).",
)
async def unlike_tweet(
    tweet_id: UUID,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    current_user: User = Depends(get_current_user),
    service: LikesService = Depends(_likes_service),
) -> LikeRelationship:
    await _enforce_like_rate_limit(current_user, redis, settings)
    result = await service.unlike(current_user, tweet_id)
    return LikeRelationship(liked=result.liked, like_count=result.like_count)
