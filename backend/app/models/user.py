"""`users` (spec §5.1): account identity + profile.

`username`/`email` are `citext` (case-insensitive text) so `"Alice"` and
`"alice"` collide at the database level, matching the spec's case-insensitive
uniqueness requirement without service-layer lower-casing tricks. GIN
trigram indexes on `username`/`name` (created in the migration, not
representable as a plain SQLModel `Field`) back fuzzy search (spec: "Fuzzy
user search uses the `pg_trgm` extension").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import CITEXT
from sqlmodel import Field

from app.models.base import UUIDPrimaryKeyMixin, timestamptz_column, utcnow

USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,30}$"
BIO_MAX_LENGTH = 160


class User(UUIDPrimaryKeyMixin, table=True):
    """A registered account. See `AUTH_*` tasks for password verification /
    session logic — this model only owns the persisted shape.
    """

    __tablename__ = "users"

    name: str = Field(nullable=False, max_length=50)
    username: str = Field(sa_column=Column(CITEXT, nullable=False, unique=True, index=True))
    email: str = Field(sa_column=Column(CITEXT, nullable=False, unique=True, index=True))
    password_hash: str = Field(nullable=False)
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    avatar_key: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
