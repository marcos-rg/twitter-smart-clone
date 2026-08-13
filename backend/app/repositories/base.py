"""Generic async repository base (spec §8.1: repositories own data access;
services own business rules on top of them).
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


class BaseRepository[ModelT: SQLModel]:
    """Thin async CRUD wrapper around one SQLModel table. Feature
    repositories subclass this for entity-specific queries (pagination,
    uniqueness lookups, counters, ...).
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: UUID) -> ModelT | None:
        """Fetch by primary key, or `None` if it doesn't exist."""
        return await self.session.get(self.model, id_)

    async def add(self, obj: ModelT) -> ModelT:
        """Stage `obj` for insert and flush it so its defaults/PK are
        populated. Does not commit — the caller's unit of work does.
        """
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        """Stage `obj` for delete and flush."""
        await self.session.delete(obj)
        await self.session.flush()

    async def count(self) -> int:
        """Total row count for the table (used sparingly — pagination uses
        the keyset `limit + 1` lookahead instead of `COUNT` for list pages).
        """
        result = await self.session.exec(select(self.model))
        return len(result.all())
