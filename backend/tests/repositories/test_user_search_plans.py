"""Query-plan evidence for exact/prefix/fuzzy user search indexes."""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.user import User


async def _seed_representative_users(db_session: AsyncSession) -> None:
    for i in range(2500):
        db_session.add(
            User(
                name=f"User {i}",
                username=f"user_{i:04d}",
                email=f"user_{i:04d}@example.com",
                password_hash="hash",
            )
        )
    db_session.add(
        User(
            name="Ada Lovelace",
            username="ada_exact_target",
            email="ada_exact_target@example.com",
            password_hash="hash",
        )
    )
    db_session.add(
        User(
            name="Searchable Person",
            username="searchable_target",
            email="searchable_target@example.com",
            password_hash="hash",
        )
    )
    await db_session.flush()


async def _explain_lines(db_session: AsyncSession, sql: str, params: dict[str, str]) -> str:
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    result = await db_session.execute(text(f"EXPLAIN (COSTS OFF) {sql}"), params)
    return "\n".join(str(line[0]) for line in result.all())


async def test_exact_search_uses_username_unique_index(db_session: AsyncSession) -> None:
    await _seed_representative_users(db_session)
    plan = await _explain_lines(
        db_session,
        "SELECT id FROM users WHERE username = :q LIMIT 1",
        {"q": "ada_exact_target"},
    )
    assert "uq_users_username" in plan or "ix_users_username" in plan


async def test_prefix_search_uses_trigram_index(db_session: AsyncSession) -> None:
    await _seed_representative_users(db_session)
    plan = await _explain_lines(
        db_session,
        "SELECT id FROM users WHERE username ILIKE :pattern ORDER BY username ASC LIMIT 20",
        {"pattern": "search%"},
    )
    assert "ix_users_username_trgm" in plan or "ix_users_username" in plan


async def test_fuzzy_search_uses_trigram_index(db_session: AsyncSession) -> None:
    await _seed_representative_users(db_session)
    plan = await _explain_lines(
        db_session,
        "SELECT id FROM users WHERE username % :q ORDER BY similarity(username, :q) DESC LIMIT 20",
        {"q": "serchable"},
    )
    assert "ix_users_username_trgm" in plan
