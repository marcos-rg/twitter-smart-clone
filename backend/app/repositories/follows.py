"""`FollowRepository` (spec §5.1: `follows`).

Duplicate follows and self-follows are rejected by the database itself (PK
+ `CHECK` constraint from the initial migration); this repository surfaces
those as a plain `IntegrityError` for the service layer to translate into
the standard `409 conflict` / `422` error envelope.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func
from sqlmodel import select

from app.models.follow import Follow
from app.repositories.base import BaseRepository


class FollowRepository(BaseRepository[Follow]):
    model = Follow

    async def get(self, follower_id: UUID, followee_id: UUID) -> Follow | None:  # type: ignore[override]
        """Fetch by the composite `(follower_id, followee_id)` key."""
        return await self.session.get(Follow, (follower_id, followee_id))

    async def exists(self, follower_id: UUID, followee_id: UUID) -> bool:
        return await self.get(follower_id, followee_id) is not None

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
