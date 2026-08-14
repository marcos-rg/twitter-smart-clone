"""`GET /feed` — the authenticated home feed (spec §6.3 "Tweets & feed",
§8.2 "Feed generation (fan-out on read)").

Built from the exact same `TweetsService` construction as
`app.routers.tweets`/`app.routers.users` (`build_tweets_service`), so a
tweet renders byte-identically whether it's reached via `/feed`,
`/tweets/{id}`, or `/users/{username}/tweets`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_current_user, get_db_session, get_redis, get_settings_dep
from app.models.user import User
from app.routers.tweets import build_tweets_service
from app.schemas.tweets import TweetListPage, TweetListResponse
from app.services.tweets import TweetsService

router = APIRouter(prefix="/api/v1", tags=["feed"])


def _tweets_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> TweetsService:
    return build_tweets_service(session, redis, settings)


@router.get(
    "/feed",
    response_model=TweetListResponse,
    summary="The authenticated user's home feed: their own tweets plus tweets from "
    "users they follow, newest first (cursor paginated).",
)
async def get_feed(
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    current_user: User = Depends(get_current_user),
    service: TweetsService = Depends(_tweets_service),
) -> TweetListResponse:
    page = await service.list_feed(current_user, cursor=cursor, limit=limit)
    return TweetListResponse(
        data=list(page.items), page=TweetListPage(next_cursor=page.next_cursor)
    )
