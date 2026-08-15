"""`TweetMediaRepository` (spec §5.1: `tweet_media`)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
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

    async def list_for_tweets(self, tweet_ids: Sequence[UUID]) -> dict[UUID, list[TweetMedia]]:
        """Batch version of `list_for_tweet`: every attachment for any of
        `tweet_ids`, grouped by `tweet_id` and kept in display order within
        each group. Used to render a page of tweets (timeline/replies)
        without one query per row.
        """
        if not tweet_ids:
            return {}
        result = await self.session.exec(
            select(TweetMedia)
            .where(TweetMedia.tweet_id.in_(tweet_ids))  # type: ignore[attr-defined]
            .order_by(TweetMedia.position.asc())  # type: ignore[attr-defined]
        )
        grouped: dict[UUID, list[TweetMedia]] = defaultdict(list)
        for media in result.all():
            grouped[media.tweet_id].append(media)
        return dict(grouped)

    async def list_already_used_keys(self, keys: Sequence[str]) -> set[str]:
        """Which of `keys` are already attached to *some* tweet (any tweet,
        any author) — a confirmed upload key must be used at most once, so
        `TweetsService.create_tweet` rejects reuse of a key from an earlier
        tweet.
        """
        if not keys:
            return set()
        result = await self.session.exec(
            select(TweetMedia.s3_key).where(TweetMedia.s3_key.in_(keys))  # type: ignore[attr-defined]
        )
        return set(result.all())
