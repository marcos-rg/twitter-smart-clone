"""Schemas for `/users/*` profile, timeline, and search endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.user import BIO_MAX_LENGTH, USERNAME_PATTERN


class SearchMode(StrEnum):
    exact = "exact"
    prefix = "prefix"
    fuzzy = "fuzzy"


class UserPublicProfile(BaseModel):
    id: UUID
    name: str
    username: str
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    avatar_key: str | None = None
    created_at: datetime
    #: Follow-graph fields (spec §5.1 `follows`, TSC-SOC-001). Defaulted so
    #: `model_validate()` from a bare ORM `User` (e.g. the `/users/me` PATCH
    #: response) still works without callers threading counts through every
    #: call site — `GET /users/{username}` is the one route that populates
    #: them with real values via `UsersService.get_profile_view`.
    followers_count: int = 0
    following_count: int = 0
    #: Whether the authenticated caller follows this profile. Always
    #: `False` on one's own profile (self-follow is impossible).
    is_following: bool = False

    model_config = {"from_attributes": True}


class UserPrivateProfile(UserPublicProfile):
    email: EmailStr


class UserProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50, examples=["Ada Lovelace"])
    username: str | None = Field(default=None, pattern=USERNAME_PATTERN, examples=["ada"])
    email: EmailStr | None = Field(default=None, examples=["ada@example.com"])
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH, examples=["Mathematician."])

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> UserProfileUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required.")
        return self


class PageInfo(BaseModel):
    next_cursor: str | None


class UserSearchItem(BaseModel):
    id: UUID
    name: str
    username: str
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    avatar_key: str | None = None

    model_config = {"from_attributes": True}


class UserSearchResponse(BaseModel):
    data: list[UserSearchItem]
    page: PageInfo


# `GET /users/{username}/tweets` (the profile timeline) is registered on
# `app.routers.users` but renders `app.schemas.tweets.TweetView` /
# `TweetListResponse` — the same shape `POST /tweets`, `GET /tweets/{id}`,
# and `GET /tweets/{id}/replies` return (TSC-TWEET-001) — rather than a
# timeline-specific DTO here.
