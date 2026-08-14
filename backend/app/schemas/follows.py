"""Schemas for `POST`/`DELETE /users/{username}/follow` and the
`/users/{username}/followers` / `/following` list endpoints (spec §6.1,
§6.3 "Follows").
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.user import BIO_MAX_LENGTH
from app.schemas.users import PageInfo


class FollowUserItem(BaseModel):
    """One row of a followers/following list — the same public shape as a
    user-search result, enough to render a user chip without a follow-up
    profile fetch.
    """

    id: UUID
    name: str
    username: str
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    avatar_key: str | None = None

    model_config = {"from_attributes": True}


class FollowListResponse(BaseModel):
    data: list[FollowUserItem]
    page: PageInfo


class FollowRelationship(BaseModel):
    """Response body of `POST`/`DELETE /users/{username}/follow`: the
    relationship after the call plus the target's updated follower count,
    so the client can update its UI from this single response instead of
    re-fetching the profile.
    """

    following: bool
    followers_count: int
