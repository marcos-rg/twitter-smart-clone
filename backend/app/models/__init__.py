"""SQLModel table models (spec §5: Data model).

Importing this package registers every table on `SQLModel.metadata`, which
Alembic's `env.py` imports for autogenerate/offline schema comparisons.
"""

from __future__ import annotations

from app.models.follow import Follow
from app.models.like import Like
from app.models.notification import Notification, NotificationType
from app.models.pending_upload import MediaPurpose, PendingUpload, PendingUploadStatus
from app.models.refresh_token import RefreshToken
from app.models.tweet import Tweet
from app.models.tweet_media import TweetMedia
from app.models.user import User

__all__ = [
    "Follow",
    "Like",
    "MediaPurpose",
    "Notification",
    "NotificationType",
    "PendingUpload",
    "PendingUploadStatus",
    "RefreshToken",
    "Tweet",
    "TweetMedia",
    "User",
]
