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


class UserTimelineItem(BaseModel):
    id: UUID
    author_id: UUID
    content: str
    parent_tweet_id: UUID | None
    like_count: int
    reply_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserTimelineResponse(BaseModel):
    data: list[UserTimelineItem]
    page: PageInfo
