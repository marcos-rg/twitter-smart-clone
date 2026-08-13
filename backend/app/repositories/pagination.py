"""Cursor-based keyset pagination helpers (spec §6.1).

The cursor is an opaque, base64-encoded token that round-trips
`(created_at, id)` of the last item on the previous page. Encoding both
fields (not just `created_at`) breaks ties between rows created in the same
timestamp tick, which a `created_at`-only cursor would silently drop or
duplicate.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, tuple_
from sqlalchemy.sql import Select

#: Requests may ask for at most this many items per page (spec §6.1: "max 50").
MAX_PAGE_SIZE = 50
#: Default page size when the caller doesn't specify one (spec §6.1: "default 20").
DEFAULT_PAGE_SIZE = 20


class InvalidCursorError(ValueError):
    """Raised when a client-supplied cursor can't be decoded."""


@dataclass(frozen=True)
class Cursor:
    """A decoded `(created_at, id)` keyset position."""

    created_at: datetime
    id: UUID


@dataclass(frozen=True)
class Page[T]:
    """A page envelope matching the spec §6.1 response shape."""

    items: Sequence[T]
    next_cursor: str | None


def encode_cursor(created_at: datetime, id_: UUID) -> str:
    """Encode `(created_at, id)` as the opaque cursor token clients see."""
    payload = json.dumps({"ts": created_at.isoformat(), "id": str(id_)})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(token: str) -> Cursor:
    """Decode a cursor token produced by `encode_cursor`.

    Raises `InvalidCursorError` for any malformed/tampered token instead of
    letting a `json.JSONDecodeError`/`KeyError`/etc. leak past this module —
    callers (routers) turn this into a single `400 validation_error`.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        return Cursor(created_at=datetime.fromisoformat(payload["ts"]), id=UUID(payload["id"]))
    except Exception as exc:  # noqa: BLE001 - any decode failure ⇒ invalid cursor
        raise InvalidCursorError("Invalid pagination cursor.") from exc


def clamp_limit(limit: int | None) -> int:
    """Clamp a requested page size into `[1, MAX_PAGE_SIZE]`."""
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))


def apply_keyset[T](
    stmt: Select[tuple[T]],
    *,
    created_at_col: ColumnElement[datetime],
    id_col: ColumnElement[UUID],
    cursor: Cursor | None,
    direction: Literal["asc", "desc"] = "desc",
) -> Select[tuple[T]]:
    """Add the `WHERE (created_at, id) < / > (cursor)` keyset predicate and
    `ORDER BY` clause for one page, in the given chronological `direction`.
    Callers fetch `limit + 1` rows so they can tell whether a next page
    exists without a separate `COUNT` query.
    """
    if direction == "desc":
        stmt = stmt.order_by(created_at_col.desc(), id_col.desc())
        if cursor is not None:
            stmt = stmt.where(tuple_(created_at_col, id_col) < (cursor.created_at, cursor.id))
    else:
        stmt = stmt.order_by(created_at_col.asc(), id_col.asc())
        if cursor is not None:
            stmt = stmt.where(tuple_(created_at_col, id_col) > (cursor.created_at, cursor.id))
    return stmt


def build_page[T](
    rows: Sequence[T],
    limit: int,
    *,
    created_at_of: object,
    id_of: object,
) -> Page[T]:
    """Turn up-to-`limit + 1` fetched `rows` into a `Page`: trims the lookahead
    row and derives `next_cursor` from the last *returned* item.

    `created_at_of`/`id_of` are callables `(T) -> value`, kept untyped as
    `object` here and cast at the call site because a `Callable[[T], X]`
    parameter confuses mypy's variance checking against `Select[tuple[T]]`
    call sites; each repository passes plain attribute-accessor lambdas.
    """
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(created_at_of(last), id_of(last))  # type: ignore[operator]
    return Page(items=items, next_cursor=next_cursor)
