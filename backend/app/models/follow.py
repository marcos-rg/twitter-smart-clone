"""`follows` (spec §5.1): a directed follow edge, `follower_id -> followee_id`.

Composite primary key `(follower_id, followee_id)` makes a duplicate follow
a primary-key violation (idempotent at the database level); the
`follower_id <> followee_id` check constraint (added in the migration —
SQLModel/SQLAlchemy `Field` has no first-class multi-column `CHECK` syntax)
rejects self-follows.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel

from app.models.base import timestamptz_column, utcnow

CHECK_NO_SELF_FOLLOW = "follower_id <> followee_id"


class Follow(SQLModel, table=True):
    """One user following another."""

    __tablename__ = "follows"

    follower_id: UUID = Field(foreign_key="users.id", primary_key=True)
    followee_id: UUID = Field(foreign_key="users.id", primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
