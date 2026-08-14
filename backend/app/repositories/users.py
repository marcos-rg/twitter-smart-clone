"""`UserRepository` (spec §5.1: `users`)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, case, func, or_
from sqlmodel import select

from app.models.user import User
from app.repositories.base import BaseRepository
from app.repositories.pagination import Page, clamp_limit


class InvalidUserSearchCursorError(ValueError):
    """Raised when a user-search cursor cannot be decoded/validated."""


@dataclass(frozen=True)
class UserSearchCursor:
    mode: str
    username: str
    id: UUID
    score: float | None = None


def encode_user_search_cursor(cursor: UserSearchCursor) -> str:
    payload: dict[str, str | float | None] = {
        "m": cursor.mode,
        "u": cursor.username,
        "id": str(cursor.id),
    }
    if cursor.score is not None:
        payload["s"] = cursor.score
    encoded = json.dumps(payload)
    return base64.urlsafe_b64encode(encoded.encode("utf-8")).decode("ascii")


def decode_user_search_cursor(token: str) -> UserSearchCursor:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        mode = payload["m"]
        username = payload["u"]
        id_ = payload["id"]
        score = payload.get("s")
        if not isinstance(mode, str):
            raise InvalidUserSearchCursorError("Invalid cursor mode.")
        if mode not in {"exact", "prefix", "fuzzy"}:
            raise InvalidUserSearchCursorError("Invalid cursor mode.")
        if not isinstance(username, str):
            raise InvalidUserSearchCursorError("Invalid cursor username.")
        if score is not None and not isinstance(score, (float, int)):
            raise InvalidUserSearchCursorError("Invalid cursor score.")
        return UserSearchCursor(
            mode=mode,
            username=username,
            id=UUID(id_),
            score=None if score is None else float(score),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise InvalidUserSearchCursorError("Invalid user search cursor.") from exc


class UserRepository(BaseRepository[User]):
    model = User

    @staticmethod
    def _table_columns() -> Any:
        return cast(Any, User).__table__.c

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

    async def search_exact(
        self, query: str, *, cursor: UserSearchCursor | None, limit: int | None
    ) -> Page[User]:
        limit = clamp_limit(limit)
        cols = self._table_columns()
        stmt = (
            select(User)
            .where(or_(cols.username == query, func.lower(cols.name) == func.lower(query)))
            .order_by(
                case((cols.username == query, 0), else_=1),
                cols.username.asc(),
                cols.id.asc(),
            )
        )
        if cursor is not None:
            if cursor.username.casefold() == query.casefold():
                stmt = stmt.where(cols.username != query)
            else:
                stmt = stmt.where(
                    or_(
                        cols.username > cursor.username,
                        and_(cols.username == cursor.username, cols.id > cursor.id),
                    )
                )
        stmt = stmt.limit(limit + 1)
        result = await self.session.exec(stmt)
        users = list(result.all())
        has_more = len(users) > limit
        items = users[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_user_search_cursor(
                UserSearchCursor(mode="exact", username=last.username, id=last.id)
            )
        return Page(items=items, next_cursor=next_cursor)

    async def search_prefix(
        self, query: str, *, cursor: UserSearchCursor | None, limit: int | None
    ) -> Page[User]:
        limit = clamp_limit(limit)
        pattern = f"{query}%"
        cols = self._table_columns()
        stmt = (
            select(User)
            .where(or_(cols.username.ilike(pattern), cols.name.ilike(pattern)))
            .order_by(cols.username.asc(), cols.id.asc())
        )
        if cursor is not None:
            stmt = stmt.where(
                or_(
                    cols.username > cursor.username,
                    and_(cols.username == cursor.username, cols.id > cursor.id),
                )
            )
        stmt = stmt.limit(limit + 1)
        result = await self.session.exec(stmt)
        users = list(result.all())
        has_more = len(users) > limit
        items = users[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_user_search_cursor(
                UserSearchCursor(mode="prefix", username=last.username, id=last.id)
            )
        return Page(items=items, next_cursor=next_cursor)

    async def search_fuzzy(
        self, query: str, *, cursor: UserSearchCursor | None, limit: int | None
    ) -> Page[User]:
        limit = clamp_limit(limit)
        cols = self._table_columns()
        similarity = func.greatest(
            func.similarity(cols.username, query), func.similarity(cols.name, query)
        )
        stmt = select(User, similarity).where(
            or_(
                cols.username.op("%")(query),
                cols.name.op("%")(query),
            )
        )
        if cursor is not None:
            if cursor.score is None:
                raise InvalidUserSearchCursorError("Fuzzy cursor must include score.")
            stmt = stmt.where(
                or_(
                    similarity < cursor.score,
                    and_(
                        similarity == cursor.score,
                        or_(
                            cols.username > cursor.username,
                            and_(
                                cols.username == cursor.username,
                                cols.id > cursor.id,
                            ),
                        ),
                    ),
                )
            )
        stmt = stmt.order_by(similarity.desc(), cols.username.asc(), cols.id.asc()).limit(limit + 1)
        result = await self.session.exec(stmt)
        rows = list(result.all())
        has_more = len(rows) > limit
        items = [row[0] for row in rows[:limit]]
        next_cursor: str | None = None
        if has_more and rows:
            last_user, last_score = rows[limit - 1]
            next_cursor = encode_user_search_cursor(
                UserSearchCursor(
                    mode="fuzzy",
                    username=last_user.username,
                    id=last_user.id,
                    score=float(last_score),
                )
            )
        return Page(items=items, next_cursor=next_cursor)

    async def search_by_name_or_username(self, query: str, *, limit: int = 20) -> list[User]:
        """Backward-compatible helper kept for existing tests."""
        page = await self.search_fuzzy(query, cursor=None, limit=limit)
        return list(page.items)
