"""`likes` (spec §5.1): composite PK `(user_id, tweet_id)` makes liking the
same tweet twice idempotent at the database level (`INSERT ... ON CONFLICT
DO NOTHING` in the repository, spec: "idempotent like").
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel

from app.models.base import timestamptz_column, utcnow


class Like(SQLModel, table=True):
    """One user liking one tweet."""

    __tablename__ = "likes"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    tweet_id: UUID = Field(foreign_key="tweets.id", primary_key=True, index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
