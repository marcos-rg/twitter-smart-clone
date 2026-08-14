"""Tests for `app.core.outbox`: the post-commit callback queue."""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.outbox import queue_post_commit, run_post_commit_callbacks


async def test_queued_callback_does_not_run_until_drained(db_session: AsyncSession) -> None:
    calls: list[str] = []

    async def callback() -> None:
        calls.append("ran")

    queue_post_commit(db_session, callback)
    assert calls == []  # merely queuing must not run it


async def test_run_post_commit_callbacks_runs_and_clears_the_queue(
    db_session: AsyncSession,
) -> None:
    calls: list[str] = []

    async def callback() -> None:
        calls.append("ran")

    queue_post_commit(db_session, callback)
    await run_post_commit_callbacks(db_session)
    assert calls == ["ran"]

    # Draining clears the queue: running again is a no-op, not a re-run.
    await run_post_commit_callbacks(db_session)
    assert calls == ["ran"]


async def test_multiple_callbacks_run_in_queued_order(db_session: AsyncSession) -> None:
    calls: list[int] = []

    def make_callback(value: int):  # type: ignore[no-untyped-def]
        async def callback() -> None:
            calls.append(value)

        return callback

    queue_post_commit(db_session, make_callback(1))
    queue_post_commit(db_session, make_callback(2))
    queue_post_commit(db_session, make_callback(3))

    await run_post_commit_callbacks(db_session)
    assert calls == [1, 2, 3]


async def test_never_running_the_drain_means_the_callback_never_fires(
    db_session: AsyncSession,
) -> None:
    """Simulates the rollback branch of `get_db_session`: a queued callback
    for a transaction that never committed simply never runs, because
    nothing ever calls `run_post_commit_callbacks`.
    """
    calls: list[str] = []

    async def callback() -> None:
        calls.append("ran")

    queue_post_commit(db_session, callback)
    await db_session.rollback()
    assert calls == []
