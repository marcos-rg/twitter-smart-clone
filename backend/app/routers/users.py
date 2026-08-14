"""`/users/*` profile, timeline, and search routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_current_user, get_db_session
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.schemas.users import (
    PageInfo,
    SearchMode,
    UserPrivateProfile,
    UserProfileUpdateRequest,
    UserPublicProfile,
    UserSearchItem,
    UserSearchResponse,
    UserTimelineItem,
    UserTimelineResponse,
)
from app.services.users import UsersService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _users_service(session: AsyncSession = Depends(get_db_session)) -> UsersService:
    return UsersService(UserRepository(session), TweetRepository(session), FollowRepository(session))


@router.get(
    "/search",
    response_model=UserSearchResponse,
    summary="Search users by exact, prefix, or fuzzy mode.",
)
async def search_users(
    q: Annotated[str, Query(min_length=1, max_length=50, examples=["ada"])],
    mode: Annotated[SearchMode, Query(examples=["prefix"])] = SearchMode.prefix,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    _: User = Depends(get_current_user),
    users_service: UsersService = Depends(_users_service),
) -> UserSearchResponse:
    page = await users_service.search_users(query=q, mode=mode, cursor=cursor, limit=limit)
    return UserSearchResponse(
        data=[UserSearchItem.model_validate(user) for user in page.items],
        page=PageInfo(next_cursor=page.next_cursor),
    )


@router.get(
    "/{username}",
    response_model=UserPublicProfile,
    summary="Get a public profile by username.",
)
async def get_profile(
    username: str,
    current_user: User = Depends(get_current_user),
    users_service: UsersService = Depends(_users_service),
) -> UserPublicProfile:
    view = await users_service.get_profile_view(username, current_user)
    return UserPublicProfile(
        id=view.user.id,
        name=view.user.name,
        username=view.user.username,
        bio=view.user.bio,
        avatar_key=view.user.avatar_key,
        created_at=view.user.created_at,
        followers_count=view.followers_count,
        following_count=view.following_count,
        is_following=view.is_following,
    )


@router.patch(
    "/me",
    response_model=UserPrivateProfile,
    summary="Edit the authenticated user's profile.",
)
async def update_my_profile(
    body: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    users_service: UsersService = Depends(_users_service),
) -> UserPrivateProfile:
    user = await users_service.update_current_user(current_user, body)
    return UserPrivateProfile.model_validate(user)


@router.get(
    "/{username}/tweets",
    response_model=UserTimelineResponse,
    summary="List a user's tweets with cursor pagination.",
)
async def get_user_tweets(
    username: str,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    _: User = Depends(get_current_user),
    users_service: UsersService = Depends(_users_service),
) -> UserTimelineResponse:
    page = await users_service.get_timeline(username=username, cursor=cursor, limit=limit)
    return UserTimelineResponse(
        data=[UserTimelineItem.model_validate(tweet) for tweet in page.items],
        page=PageInfo(next_cursor=page.next_cursor),
    )
