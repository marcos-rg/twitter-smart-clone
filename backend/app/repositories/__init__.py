"""Async repositories (spec §8.1): typed data-access layer on top of the
SQLModel table models in `app.models`. Services compose these; no business
rules live here beyond what the database itself enforces.
"""

from __future__ import annotations

from app.repositories.base import BaseRepository
from app.repositories.follows import FollowRepository
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.tweet_media import TweetMediaRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository

__all__ = [
    "BaseRepository",
    "FollowRepository",
    "LikeRepository",
    "NotificationRepository",
    "RefreshTokenRepository",
    "TweetMediaRepository",
    "TweetRepository",
    "UserRepository",
]
