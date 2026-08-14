"""`/tweets/*` create, get, and replies routes (spec §6.3 "Tweets & feed").

`GET /users/{username}/tweets` (the profile timeline) is registered on
`app.routers.users` — same URL prefix, same underlying `TweetsService` — but
lives there so all `/users/*` routes stay in one router module.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_current_user, get_db_session, get_redis, get_settings_dep
from app.core.rate_limit import check_rate_limit
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.pending_uploads import PendingUploadRepository
from app.repositories.tweet_media import TweetMediaRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.schemas.tweets import TweetCreateRequest, TweetListPage, TweetListResponse, TweetView
from app.services.notifications import NotificationsService
from app.services.tweets import TweetsService

router = APIRouter(prefix="/api/v1/tweets", tags=["tweets"])


def build_tweets_service(session: AsyncSession, redis: Redis, settings: Settings) -> TweetsService:
    """Shared constructor so `app.routers.users`'s timeline route and
    `app.routers.feed`'s home-feed route build the exact same service (and
    thus render the exact same `TweetView` shape) as this router's
    create/get/replies routes.
    """
    notifications_service = NotificationsService(
        NotificationRepository(session), UserRepository(session), session, redis
    )
    return TweetsService(
        TweetRepository(session),
        TweetMediaRepository(session),
        PendingUploadRepository(session),
        UserRepository(session),
        LikeRepository(session),
        notifications_service,
        follows=FollowRepository(session),
        redis=redis,
        feed_cache_ttl_seconds=settings.feed_cache_ttl_seconds,
    )


def _tweets_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> TweetsService:
    return build_tweets_service(session, redis, settings)


@router.post("", response_model=TweetView, status_code=201, summary="Create a tweet or reply.")
async def create_tweet(
    body: TweetCreateRequest,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    current_user: User = Depends(get_current_user),
    service: TweetsService = Depends(_tweets_service),
) -> TweetView:
    await check_rate_limit(
        redis,
        key=f"tweet:{current_user.id}",
        limit=settings.tweet_rate_limit_per_minute,
        window_seconds=60,
    )
    return await service.create_tweet(
        current_user,
        content=body.content,
        parent_tweet_id=body.parent_tweet_id,
        media_keys=body.media_keys,
    )


@router.get("/{tweet_id}", response_model=TweetView, summary="Get a tweet by id.")
async def get_tweet(
    tweet_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TweetsService = Depends(_tweets_service),
) -> TweetView:
    return await service.get_tweet(tweet_id, current_user)


@router.get(
    "/{tweet_id}/replies",
    response_model=TweetListResponse,
    summary="List flat replies to a tweet (paginated, oldest first).",
)
async def list_replies(
    tweet_id: UUID,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    current_user: User = Depends(get_current_user),
    service: TweetsService = Depends(_tweets_service),
) -> TweetListResponse:
    page = await service.list_replies(tweet_id, current_user, cursor=cursor, limit=limit)
    return TweetListResponse(
        data=list(page.items), page=TweetListPage(next_cursor=page.next_cursor)
    )
