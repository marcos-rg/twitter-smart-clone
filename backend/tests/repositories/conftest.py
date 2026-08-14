"""Fixtures for repository/migration integration tests: a real async
PostgreSQL engine/session, migrated to `head` once per test session, with
every table truncated before each test for isolation (spec: "Repository and
migration integration tests pass against real PostgreSQL").

`TEST_DATABASE_URL` defaults to `DATABASE_URL` (already `postgres:5432` inside
the `backend`/CI container via `docker-compose.yml`, matching the
`postgres`/`unreachable_settings` split documented in `tests/conftest.py`),
falling back to `localhost:5432` when neither is set (bare-host runs).
Running this suite truncates demo data: re-run `make seed` afterwards if you
need it back.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://twitter_smart_clone:twitter_smart_clone_dev"
        "@localhost:5432/twitter_smart_clone",
    ),
)

#: Truncated (in FK-safe order isn't required with CASCADE) before every test.
TABLES = (
    "notifications",
    "refresh_tokens",
    "likes",
    "follows",
    "tweet_media",
    "tweets",
    "users",
)


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema() -> None:
    """Upgrade the test database to `head` once before any test runs."""
    command.upgrade(_alembic_config(), "head")


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A fresh `AsyncSession` against the (already-migrated) test database,
    with every table truncated first so each test starts from empty.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)} CASCADE"))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()
