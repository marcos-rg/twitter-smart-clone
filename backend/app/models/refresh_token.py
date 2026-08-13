"""`refresh_tokens` (spec §5.1): rotation + revocation for refresh-token auth.

Only `token_hash` (never the raw token) is persisted — the raw refresh token
is a bearer secret handed to the client (httpOnly cookie); hashing it here
means a database leak alone can't be replayed as a valid refresh token.
`revoked_at` supports rotation (the old token is revoked the moment it's
exchanged for a new one) and logout-everywhere revocation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field

from app.models.base import UUIDPrimaryKeyMixin, timestamptz_column, utcnow


class RefreshToken(UUIDPrimaryKeyMixin, table=True):
    """One issued refresh token (hashed) for `user_id`."""

    __tablename__ = "refresh_tokens"

    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    token_hash: str = Field(nullable=False, unique=True, index=True)
    expires_at: datetime = Field(sa_column=timestamptz_column(nullable=False))
    revoked_at: datetime | None = Field(default=None, sa_column=timestamptz_column(nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
