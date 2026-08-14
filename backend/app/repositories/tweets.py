"""`TweetRepository` (spec §5.1: `tweets`).

Backs the three list shapes the spec's indexes are built for: a user's own
tweets (`(author_id, created_at desc)`), replies to one tweet
(`(parent_tweet_id, created_at asc)`), and the global/home feed ordering
(`(created_at desc)`).
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select

from app.models.tweet import Tweet
from app.repositories.base import BaseRepository
from app.repositories.pagination import Cursor, Page, apply_keyset, build_page, clamp_limit


class TweetRepository(BaseRepository[Tweet]):
    model = Tweet

    async def list_by_author(
        self, author_id: UUID, *, cursor: Cursor | None, limit: int | None
    ) -> Page[Tweet]:
        """A user's tweets (including their replies), newest first."""
        limit = clamp_limit(limit)
        stmt = apply_keyset(
            select(Tweet).where(Tweet.author_id == author_id),
            created_at_col=Tweet.created_at,  # type: ignore[arg-type]
            id_col=Tweet.id,  # type: ignore[arg-type]
            cursor=cursor,
            direction="desc",
        ).limit(limit + 1)
        result = await self.session.exec(stmt)  # type: ignore[call-overload]
        rows = list(result.all())
        return build_page(rows, limit, created_at_of=lambda t: t.created_at, id_of=lambda t: t.id)

    async def list_replies(
        self, parent_tweet_id: UUID, *, cursor: Cursor | None, limit: int | None
    ) -> Page[Tweet]:
        """Flat replies to `parent_tweet_id`, oldest first (thread reading order)."""
        limit = clamp_limit(limit)
        stmt = apply_keyset(
            select(Tweet).where(Tweet.parent_tweet_id == parent_tweet_id),
            created_at_col=Tweet.created_at,  # type: ignore[arg-type]
            id_col=Tweet.id,  # type: ignore[arg-type]
            cursor=cursor,
            direction="asc",
        ).limit(limit + 1)
        result = await self.session.exec(stmt)  # type: ignore[call-overload]
        rows = list(result.all())
        return build_page(rows, limit, created_at_of=lambda t: t.created_at, id_of=lambda t: t.id)

    async def list_feed(
        self, author_ids: list[UUID], *, cursor: Cursor | None, limit: int | None
    ) -> Page[Tweet]:
        """Reverse-chronological tweets authored by any of `author_ids`
        (fan-out-on-read home feed, spec §8.2).
        """
        limit = clamp_limit(limit)
        stmt = apply_keyset(
            select(Tweet).where(Tweet.author_id.in_(author_ids)),  # type: ignore[attr-defined]
            created_at_col=Tweet.created_at,  # type: ignore[arg-type]
            id_col=Tweet.id,  # type: ignore[arg-type]
            cursor=cursor,
            direction="desc",
        ).limit(limit + 1)
        result = await self.session.exec(stmt)  # type: ignore[call-overload]
        rows = list(result.all())
        return build_page(rows, limit, created_at_of=lambda t: t.created_at, id_of=lambda t: t.id)

    async def increment_reply_count(self, tweet_id: UUID) -> None:
        """Bump `reply_count` on the parent tweet (called in the same
        transaction as the reply insert, spec §5.3).
        """
        tweet_table = cast(Any, Tweet).__table__
        await self.session.exec(
            tweet_table.update()
            .where(Tweet.id == tweet_id)
            .values(reply_count=Tweet.reply_count + 1)
        )
        await self.session.flush()

    async def increment_like_count(self, tweet_id: UUID, *, delta: int = 1) -> None:
        """Adjust `like_count` by `delta` (positive on like, negative on unlike)."""
        tweet = await self.get(tweet_id)
        if tweet is not None:
            tweet.like_count += delta
            self.session.add(tweet)
            await self.session.flush()

    async def count_top_level_by_author(self, author_id: UUID) -> int:
        """How many non-reply tweets `author_id` has posted. Used by the
        idempotent seed script to decide whether it already created this
        author's demo tweets on a previous run.
        """
        result = await self.session.exec(
            select(func.count())
            .select_from(Tweet)
            .where(
                Tweet.author_id == author_id,
                Tweet.parent_tweet_id.is_(None),  # type: ignore[union-attr]
            )
        )
        return int(result.one())

    async def get_reply_by_author(self, parent_tweet_id: UUID, author_id: UUID) -> Tweet | None:
        """The reply `author_id` made to `parent_tweet_id`, if any. Used by
        the seed script to avoid inserting a duplicate demo reply.
        """
        result = await self.session.exec(
            select(Tweet).where(
                Tweet.parent_tweet_id == parent_tweet_id, Tweet.author_id == author_id
            )
        )
        return result.first()
