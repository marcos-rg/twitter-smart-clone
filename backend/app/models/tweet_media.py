"""`tweet_media` (spec §5.1): up to 4 ordered media attachments per tweet."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Field

from app.models.base import UUIDPrimaryKeyMixin

ALLOWED_CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")
MAX_POSITION = 3


class TweetMedia(UUIDPrimaryKeyMixin, table=True):
    """One image attached to a tweet, stored in S3/MinIO under `s3_key`."""

    __tablename__ = "tweet_media"

    tweet_id: UUID = Field(foreign_key="tweets.id", nullable=False, index=True)
    s3_key: str = Field(nullable=False)
    content_type: str = Field(nullable=False)
    position: int = Field(nullable=False)
