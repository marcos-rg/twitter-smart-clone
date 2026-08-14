"""`LikeRepository` (spec §5.1: `likes`).

`like()` is idempotent (`INSERT ... ON CONFLICT DO NOTHING` on the composite
PK), matching the spec's "idempotent like" note without the service layer
needing a check-then-insert race.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from app.models.base import utcnow
from app.models.like import Like
from app.repositories.base import BaseRepository


class LikeRepository(BaseRepository[Like]):
    model = Like

    async def get(self, user_id: UUID, tweet_id: UUID) -> Like | None:  # type: ignore[override]
        return await self.session.get(Like, (user_id, tweet_id))

    async def exists(self, user_id: UUID, tweet_id: UUID) -> bool:
        return await self.get(user_id, tweet_id) is not None

    async def list_liked_tweet_ids(self, user_id: UUID, tweet_ids: Sequence[UUID]) -> set[UUID]:
        """Which of `tweet_ids` `user_id` has liked — batch form of
        `exists()`, used to resolve `liked_by_viewer` for a whole page of
        tweets in one query instead of one per row.
        """
        if not tweet_ids:
            return set()
        result = await self.session.exec(
            select(Like.tweet_id).where(
                Like.user_id == user_id,
                Like.tweet_id.in_(tweet_ids),  # type: ignore[attr-defined]
            )
        )
        return set(result.all())

    async def like(self, user_id: UUID, tweet_id: UUID) -> bool:
        """Insert the like, ignoring the conflict if it already exists.
        Returns whether a new row was actually inserted (so the caller
        knows whether to bump `tweets.like_count`).
        """
        # `Like.user_id`/`.tweet_id` are typed as plain `UUID` at class scope
        # (no SQLModel-aware mypy plugin), so passing them where a
        # `ColumnElement`/`DDLConstraintColumnRole` is expected doesn't
        # type-check even though it's exactly how SQLAlchemy expects it at
        # runtime.
        stmt = (
            pg_insert(Like)
            .values(user_id=user_id, tweet_id=tweet_id, created_at=utcnow())
            .on_conflict_do_nothing(
                index_elements=[Like.user_id, Like.tweet_id]  # type: ignore[list-item]
            )
            .returning(Like.user_id)  # type: ignore[call-overload]
        )
        result = await self.session.exec(stmt)
        inserted = result.first() is not None
        await self.session.flush()
        return inserted

    async def unlike(self, user_id: UUID, tweet_id: UUID) -> bool:
        """Remove a like if it exists. Returns whether a row was deleted."""
        like = await self.get(user_id, tweet_id)
        if like is None:
            return False
        await self.delete(like)
        return True

    async def count_for_tweet(self, tweet_id: UUID) -> int:
        result = await self.session.exec(
            select(func.count()).select_from(Like).where(Like.tweet_id == tweet_id)
        )
        return int(result.one())
