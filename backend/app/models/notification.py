"""`notifications` (spec §5.1): a follow/like/reply event delivered to
`recipient_id`, triggered by `actor_id`. `type` is a native PostgreSQL enum
(`notification_type`) rather than free text, so invalid values are rejected
by the database itself.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import UUIDPrimaryKeyMixin, timestamptz_column, utcnow


class NotificationType(StrEnum):
    """The three notification-triggering events in scope (spec §5.1)."""

    FOLLOW = "follow"
    LIKE = "like"
    REPLY = "reply"


class Notification(UUIDPrimaryKeyMixin, table=True):
    """One notification for `recipient_id`, caused by `actor_id`."""

    __tablename__ = "notifications"

    recipient_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    actor_id: UUID = Field(foreign_key="users.id", nullable=False)
    type: NotificationType = Field(
        sa_column=Column(
            SAEnum(
                NotificationType,
                name="notification_type",
                native_enum=True,
                # Bind/reflect the enum's *values* ("follow"/"like"/"reply",
                # matching the migration's `postgresql.ENUM("follow", ...)`
                # labels), not its Python member names ("FOLLOW"/...) — the
                # default `values_callable` uses `.name`, which would send
                # "FOLLOW" and fail with `invalid input value for enum`.
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
            ),
            nullable=False,
        )
    )
    tweet_id: UUID | None = Field(default=None, foreign_key="tweets.id")
    is_read: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
