"""`tweets` (spec §5.1): a post, or (when `parent_tweet_id` is set) a flat
reply to one. `like_count`/`reply_count` are denormalized counters updated
in the same transaction as the like/reply insert (spec §5.3), each via an
atomic `UPDATE ... SET x = x + delta` (see `TweetRepository.increment_like_count`/
`increment_reply_count`) rather than a read-modify-write; `app.workers.reconcile_counters`
(`TSC-LIKE-001`) is the periodic Celery safety net that repairs any drift in
either counter.

The "a reply cannot itself have replies" invariant (flat, depth-1 replies
only) is a service-layer rule, not a database constraint, per spec §5.1 —
enforcing "does `parent_tweet_id` point at a top-level tweet" would need a
subquery a `CHECK` constraint cannot express.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field

from app.models.base import UUIDPrimaryKeyMixin, timestamptz_column, utcnow

CONTENT_MAX_LENGTH = 280


class Tweet(UUIDPrimaryKeyMixin, table=True):
    """A tweet or a flat reply (`parent_tweet_id IS NOT NULL`)."""

    __tablename__ = "tweets"

    author_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    content: str = Field(nullable=False, max_length=CONTENT_MAX_LENGTH)
    parent_tweet_id: UUID | None = Field(default=None, foreign_key="tweets.id", index=True)
    like_count: int = Field(default=0, nullable=False)
    reply_count: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
    deleted_at: datetime | None = Field(default=None, sa_column=timestamptz_column(nullable=True))
