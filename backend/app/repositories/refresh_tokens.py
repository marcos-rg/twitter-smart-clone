"""`RefreshTokenRepository` (spec §5.1: `refresh_tokens`; rotation + revocation)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import select

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.exec(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.first()

    async def revoke(self, token: RefreshToken) -> None:
        """Mark `token` revoked (rotation: the old token in a refresh chain
        is revoked the instant it's exchanged for a new one).
        """
        token.revoked_at = datetime.now(UTC)
        self.session.add(token)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Logout-everywhere: revoke every still-active token for `user_id`."""
        result = await self.session.exec(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        )
        now = datetime.now(UTC)
        for token in result.all():
            token.revoked_at = now
            self.session.add(token)
        await self.session.flush()

    def is_active(self, token: RefreshToken) -> bool:
        """Whether `token` hasn't been revoked or expired yet."""
        now = datetime.now(UTC)
        return token.revoked_at is None and token.expires_at > now
