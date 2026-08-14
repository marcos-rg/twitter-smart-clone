"""`UserRepository` (spec §5.1: `users`)."""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlmodel import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        """Case-insensitive lookup by username (the `citext` column already
        normalizes comparisons; no `.lower()` needed on either side).
        """
        result = await self.session.exec(select(User).where(User.username == username))
        return result.first()

    async def get_by_email(self, email: str) -> User | None:
        """Case-insensitive lookup by email."""
        result = await self.session.exec(select(User).where(User.email == email))
        return result.first()

    async def search_by_name_or_username(self, query: str, *, limit: int = 20) -> list[User]:
        """Fuzzy search over `username`/`name` using the `pg_trgm` similarity
        operator (`%`), backed by the GIN trigram indexes from the initial
        migration (spec: "Fuzzy user search uses the `pg_trgm` extension").
        """
        similarity = func.greatest(
            func.similarity(User.username, query), func.similarity(User.name, query)
        )
        stmt = (
            select(User)
            # `Model.column` is typed as its plain Python type (e.g. `str`) at
            # class scope without a SQLModel-aware mypy plugin, so `.op(...)`
            # (a `ColumnElement`-only method) doesn't type-check even though
            # it works at runtime against the real instrumented attribute.
            .where(
                or_(
                    User.username.op("%")(query),  # type: ignore[attr-defined]
                    User.name.op("%")(query),  # type: ignore[attr-defined]
                )
            )
            .order_by(similarity.desc())
            .limit(limit)
        )
        result = await self.session.exec(stmt)
        return list(result.all())
