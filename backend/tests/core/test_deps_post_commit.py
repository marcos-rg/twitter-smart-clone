"""Integration test for `get_db_session`'s post-commit outbox wiring
(`app.core.deps`): a queued callback must run once the transaction commits
— whether that's the normal success path or a handled `AppError` — and must
never run at all when the transaction rolls back after an unexpected
exception.

This is the generic platform guarantee `TSC-NOTIF-001`'s "notification rows
commit before publication and failed transactions publish nothing"
acceptance criterion rests on; it's exercised here against toy routes (no
notification feature code involved) so the guarantee is verified at the
layer that actually provides it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_db_session
from app.core.errors import AppError, register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.core.outbox import queue_post_commit
from app.core.resources import create_lifespan


class _Conflict(AppError):
    status_code = 409
    code = "conflict"


def _build_app(settings: Settings, calls: list[str]) -> FastAPI:
    app = FastAPI(lifespan=create_lifespan(settings))
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.post("/commit-ok")
    async def commit_ok(session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
        async def callback() -> None:
            calls.append("commit-ok")

        queue_post_commit(session, callback)
        return {"ok": True}

    @app.post("/commit-app-error")
    async def commit_app_error(session: AsyncSession = Depends(get_db_session)) -> None:
        async def callback() -> None:
            calls.append("commit-app-error")

        queue_post_commit(session, callback)
        raise _Conflict("expected handled error")

    @app.post("/rollback")
    async def rollback(session: AsyncSession = Depends(get_db_session)) -> None:
        async def callback() -> None:
            calls.append("rollback")

        queue_post_commit(session, callback)
        raise RuntimeError("unexpected bug")

    return app


@pytest_asyncio.fixture
async def calls() -> list[str]:
    return []


@pytest_asyncio.fixture
async def async_client(test_settings: Settings, calls: list[str]) -> AsyncIterator[AsyncClient]:
    app = _build_app(test_settings, calls)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_callback_runs_after_a_successful_commit(
    async_client: AsyncClient, calls: list[str]
) -> None:
    response = await async_client.post("/commit-ok")
    assert response.status_code == 200
    assert calls == ["commit-ok"]


async def test_callback_runs_after_a_handled_app_error_still_commits(
    async_client: AsyncClient, calls: list[str]
) -> None:
    """`AppError` is expected 4xx control flow that still commits (e.g. a
    conflict raised after a deliberate mutation) — its queued callback must
    still fire, exactly once.
    """
    response = await async_client.post("/commit-app-error")
    assert response.status_code == 409
    assert calls == ["commit-app-error"]


async def test_callback_never_runs_when_an_unexpected_exception_rolls_back(
    async_client: AsyncClient, calls: list[str]
) -> None:
    response = await async_client.post("/rollback")
    assert response.status_code == 500
    assert calls == []
