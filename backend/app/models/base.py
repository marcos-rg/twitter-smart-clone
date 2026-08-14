"""Shared model conventions (spec §5): UUIDv7 primary keys and UTC
timestamps.

Every table's primary key is a time-sortable **UUIDv7** (RFC 9562) rather
than a random UUIDv4, so rows are naturally ordered by insertion time (e.g.
`tweets.id` doubles as a chronological cursor) without needing a separate
`created_at` index for that purpose. `uuid6.uuid7()` returns a real
`uuid.UUID` instance (it subclasses it), so it round-trips through
SQLAlchemy's/PostgreSQL's native `UUID` column type with no custom type
decorator required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel
from uuid6 import uuid7


def new_uuid7() -> UUID:
    """Default factory for UUIDv7 primary keys."""
    return uuid7()


def utcnow() -> datetime:
    """Default factory for `timestamptz` columns: timezone-aware UTC now."""
    return datetime.now(UTC)


def timestamptz_column(*, nullable: bool = False) -> Column[datetime]:
    """A `TIMESTAMP WITH TIME ZONE` column.

    SQLModel maps a plain `datetime` field to `TIMESTAMP WITHOUT TIME ZONE`
    by default, which rejects the timezone-aware `datetime.now(UTC)` values
    this codebase writes everywhere (asyncpg raises `DataError: can't
    subtract offset-naive and offset-aware datetimes`). Every `datetime`
    column must go through this helper instead of a bare `Field(...)` to
    get the `timestamptz` type spec §5.1 specifies for every table.
    """
    return Column(DateTime(timezone=True), nullable=nullable)


class UUIDPrimaryKeyMixin(SQLModel):
    """A UUIDv7 `id` primary key, generated client-side so new rows have a
    known id before the INSERT round-trips (useful for repositories that
    return the created entity without a second SELECT).
    """

    id: UUID = Field(default_factory=new_uuid7, primary_key=True)


# `created_at`/`updated_at` are declared directly on each table model (see
# `Tweet`, `Follow`, `Like`, `Notification`, `User`, `RefreshToken`) rather
# than via a shared mixin: `Field(sa_column=timestamptz_column())` holds a
# live SQLAlchemy `Column` instance, and a single instance can't be attached
# to more than one `Table` — a mixin would make every subclass share (and
# fight over) the same `Column` object. Every model instead calls
# `timestamptz_column()` itself so each gets its own `Column`.
