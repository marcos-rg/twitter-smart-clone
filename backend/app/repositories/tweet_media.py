"""`TweetMediaRepository` (spec §5.1: `tweet_media`)."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import select

from app.models.tweet_media import TweetMedia
from app.repositories.base import BaseRepository


class TweetMediaRepository(BaseRepository[TweetMedia]):
    model = TweetMedia

    async def list_for_tweet(self, tweet_id: UUID) -> list[TweetMedia]:
        """Every attachment for `tweet_id`, in display order."""
        result = await self.session.exec(
            select(TweetMedia).where(TweetMedia.tweet_id == tweet_id)
            # `.position` is typed as plain `int` at class scope (no
            # SQLModel-aware mypy plugin), so `.asc()` (a `ColumnElement`
            # method) doesn't type-check even though it works at runtime.
            .order_by(TweetMedia.position.asc())  # type: ignore[attr-defined]
        )
        return list(result.all())
