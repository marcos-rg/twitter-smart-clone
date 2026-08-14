"""Request/response schemas for `/auth/*` (spec §6.3, §7.1).

These are the request-validation and response-shaping layer: routers depend
on `app.services.auth.AuthService` for the actual business logic and only use
these `Pydantic`/`SQLModel` models to (de)serialize the HTTP boundary.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.user import BIO_MAX_LENGTH, USERNAME_PATTERN


class RegisterRequest(BaseModel):
    """`POST /auth/register` body."""

    name: str = Field(min_length=1, max_length=50, examples=["Ada Lovelace"])
    username: str = Field(pattern=USERNAME_PATTERN, examples=["ada"])
    email: EmailStr = Field(examples=["ada@example.com"])
    password: str = Field(min_length=8, max_length=128, examples=["correct horse battery staple"])


class LoginRequest(BaseModel):
    """`POST /auth/login` body."""

    email: EmailStr = Field(examples=["ada@example.com"])
    password: str = Field(min_length=1, max_length=128, examples=["correct horse battery staple"])


class UserPublic(BaseModel):
    """The current-user shape returned by `/auth/register`, `/auth/me`, and
    embedded in the `/auth/login` response.
    """

    id: UUID
    name: str
    username: str
    email: EmailStr
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    avatar_key: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessTokenResponse(BaseModel):
    """`POST /auth/login` and `POST /auth/refresh` response body: the access
    token (spec §7.1: "returned in the login/refresh response body"). The
    refresh token itself never appears in a response body — only as the
    httpOnly cookie.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")
    user: UserPublic | None = Field(
        default=None, description="Present on /auth/login, omitted on /auth/refresh."
    )
