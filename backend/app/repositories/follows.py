"""`FollowRepository` (spec §5.1: `follows`).

Duplicate follows and self-follows are rejected by the database itself (PK
+ `CHECK` constraint from the initial migration); this repository surfaces
those as a plain `IntegrityError` for the service layer to translate into
the standard `409 conflict` / `422` error envelope, except for `follow()`
itself, which treats a PK-violation race as "already following" (see its
docstring) so the idempotent-follow contract holds even under concurrency.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.follow import Follow
from app.repositories.base import BaseRepository
from app.repositories.pagination import Cursor, Page, apply_keyset, build_page, clamp_limit


class FollowRepository(BaseRepository[Follow]):
    model = Follow

    async def get(self, follower_id: UUID, followee_id: UUID) -> Follow | None:  # type: ignore[override]
        """Fetch by the composite `(follower_id, followee_id)` key."""
        return await self.session.get(Follow, (follower_id, followee_id))

    async def exists(self, follower_id: UUID, followee_id: UUID) -> bool:
        return await self.get(follower_id, followee_id) is not None

    async def follow(self, follower_id: UUID, followee_id: UUID) -> bool:
        """Create the `(follower_id, followee_id)` edge if it doesn't already
        exist. Returns whether a *new* row was inserted — `False` on a
        repeat call, which is the idempotent-follow contract the service
        layer relies on (a repeat follow never creates a second edge or a
        second notification).

        The `exists()` pre-check handles the common case cheaply without
        touching the outer transaction. A `SAVEPOINT` (`begin_nested`)
        around the insert also makes this safe under a genuine race — two
        concurrent `follow()` calls for the same pair can both pass the
        pre-check before either commits — by catching the loser's
        primary-key violation here and treating it as "already following"
        instead of letting it propagate and poison the caller's outer
        transaction/request.

        Self-follows are rejected by the service layer *before* this is
        ever called (that check is never a race — it only depends on the
        caller's own id vs. the target's), so any `IntegrityError` reaching
        this method is always the duplicate-follow race, never the
        `CHECK (follower_id <> followee_id)` constraint.
        """
        if await self.exists(follower_id, followee_id):
            return False
        try:
            async with self.session.begin_nested():
                self.session.add(Follow(follower_id=follower_id, followee_id=followee_id))
                await self.session.flush()
        except IntegrityError:
            return False
        return True

    async def unfollow(self, follower_id: UUID, followee_id: UUID) -> bool:
        """Remove a follow edge if it exists. Returns whether a row was
        deleted (idempotent unfollow: unfollowing twice isn't an error).
        """
        follow = await self.get(follower_id, followee_id)
        if follow is None:
            return False
        await self.delete(follow)
        return True

    async def count_followers(self, user_id: UUID) -> int:
        result = await self.session.exec(
            select(func.count()).select_from(Follow).where(Follow.followee_id == user_id)
        )
        return int(result.one())

    async def count_following(self, user_id: UUID) -> int:
        result = await self.session.exec(
            select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
        )
        return int(result.one())

    async def list_followers(
        self, user_id: UUID, *, cursor: Cursor | None, limit: int | None
    ) -> Page[Follow]:
        """Follow edges where `user_id` is the followee (i.e. its
        followers), newest follow first.

        Returns `Follow` rows, not `User`s — callers batch-resolve the
        follower `User` rows themselves (mirrors
        `NotificationRepository.list_for_recipient` + the service-level
        actor resolution in `NotificationsService.list_for_recipient`), so
        this repository stays single-table and one query.
        """
        limit = clamp_limit(limit)
        stmt = apply_keyset(
            select(Follow).where(Follow.followee_id == user_id),
            created_at_col=Follow.created_at,  # type: ignore[arg-type]
            id_col=Follow.follower_id,  # type: ignore[arg-type]
            cursor=cursor,
            direction="desc",
        ).limit(limit + 1)
        result = await self.session.exec(stmt)  # type: ignore[call-overload]
        rows = list(result.all())
        return build_page(
            rows, limit, created_at_of=lambda f: f.created_at, id_of=lambda f: f.follower_id
        )

    async def list_followee_ids(self, user_id: UUID) -> list[UUID]:
        """Every id `user_id` follows, unpaginated (no `created_at`/keyset
        ordering — the caller only needs set membership). Backs the home
        feed's author set (spec §8.2: "queries tweets authored by the set of
        users the requester follows"), which needs the *whole* following set
        in one shot rather than a paginated followers/following listing page
        at a time.
        """
        result = await self.session.exec(
            select(Follow.followee_id).where(Follow.follower_id == user_id)
        )
        return list(result.all())

    async def list_following(
        self, user_id: UUID, *, cursor: Cursor | None, limit: int | None
    ) -> Page[Follow]:
        """Follow edges where `user_id` is the follower (i.e. who it
        follows), newest follow first.
        """
        limit = clamp_limit(limit)
        stmt = apply_keyset(
            select(Follow).where(Follow.follower_id == user_id),
            created_at_col=Follow.created_at,  # type: ignore[arg-type]
            id_col=Follow.followee_id,  # type: ignore[arg-type]
            cursor=cursor,
            direction="desc",
        ).limit(limit + 1)
        result = await self.session.exec(stmt)  # type: ignore[call-overload]
        rows = list(result.all())
        return build_page(
            rows, limit, created_at_of=lambda f: f.created_at, id_of=lambda f: f.followee_id
        )
