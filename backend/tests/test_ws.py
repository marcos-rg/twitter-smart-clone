"""Integration tests for `GET /api/v1/ws` (`TSC-NOTIF-004`, spec §4.2, §4.3
"WebSocket tests: connect, auth rejection, receive a notification within the
latency budget").

Runs against a real PostgreSQL + Redis (see `tests/repositories/conftest.py`
/ `tests/test_notifications.py` for the same convention), using the
synchronous `fastapi.testclient.TestClient` — the standard way to drive
FastAPI's `@router.websocket` handlers, including the handshake-rejection
path exercised here.

Notification creation goes through the real `NotificationsService` +
post-commit outbox (mirroring `tests/services/test_notifications_service.py`)
so these tests exercise the full "DB commit -> Redis PUBLISH -> WS push"
pipeline end to end, not just the transport layer in isolation.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocketDisconnect

from alembic import command
from app.core.config import Settings
from app.core.outbox import run_post_commit_callbacks
from app.main import create_app
from app.models.notification import NotificationType
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRepository
from app.services.notifications import NotificationsService
from tests.repositories.conftest import _alembic_config

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_ws() -> None:
    command.upgrade(_alembic_config(), "head")


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://twitter_smart_clone:twitter_smart_clone_dev"
        "@localhost:5432/twitter_smart_clone",
    ),
)


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


def _ws_settings(**overrides: object) -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="ws-test-secret",
        auth_rate_limit_per_minute=1000,
        **overrides,  # type: ignore[arg-type]
    )


def _register(client: TestClient, **field_overrides: str) -> dict[str, str]:
    suffix = _unique_suffix()
    payload = {
        "name": "Ada Lovelace",
        "username": f"ws{suffix}",
        "email": f"ws{suffix}@example.com",
        "password": "correct horse battery staple",
    }
    payload.update(field_overrides)
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


def _login(client: TestClient, *, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token: str = response.json()["access_token"]
    return token


def _call_with_timeout[T](fn: Callable[[], T], *, timeout: float) -> T:
    """Run a blocking call (a `TestClient` WebSocket `receive*()`) on a
    worker thread with a hard wall-clock timeout, so a transport bug that
    would otherwise hang the socket read hangs this helper instead — and
    fails with a clear message rather than stalling the whole test run.
    """
    result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def _target() -> None:
        try:
            result.put((True, fn()))
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread below
            result.put((False, exc))

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    try:
        ok, value = result.get(timeout=timeout)
    except queue.Empty:
        pytest.fail(f"no WebSocket message received within {timeout}s")
    if not ok:
        raise value
    return value  # type: ignore[no-any-return]


async def _create_and_publish_notification(
    *,
    database_url: str,
    redis_url: str,
    recipient_username: str,
    actor_username: str,
    type_: NotificationType = NotificationType.FOLLOW,
) -> UUID:
    """Create a real notification row for `recipient_username` (triggered by
    `actor_username`) through `NotificationsService`, commit, and drain the
    post-commit outbox — the exact sequence `get_db_session` runs for a real
    request (see `app.core.outbox`) — so the Redis `PUBLISH` this test
    observes is the real production path, not a hand-rolled shortcut.
    """
    engine = create_async_engine(database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sessionmaker() as session:
            users = UserRepository(session)
            recipient = await users.get_by_username(recipient_username)
            actor = await users.get_by_username(actor_username)
            assert recipient is not None
            assert actor is not None
            service = NotificationsService(NotificationRepository(session), users, session, redis)
            notification = await service.create_notification(
                recipient_id=recipient.id, actor=actor, type_=type_, tweet_id=None
            )
            assert notification is not None
            await session.commit()
            await run_post_commit_callbacks(session)
            return notification.id
    finally:
        await redis.aclose()
        await engine.dispose()


def _wait_bridge_subscribed(client: TestClient, app: FastAPI) -> None:
    """Block until this process's `NotificationRedisBridge` has actually
    completed `PSUBSCRIBE` against the real test Redis.

    `WebSocketRuntime.start()` (called from the app's lifespan) launches the
    bridge's connect-and-retry loop without waiting for the first subscribe
    to land (`app.ws.redis_bridge`: "Connections are lazy ... so the app can
    still start even if a dependency is temporarily down"). Without this
    wait, a test that publishes immediately after `TestClient.__enter__`
    could race the bridge's own subscribe and lose the message forever —
    Redis pub/sub never redelivers to a subscriber that joined too late.
    `client.portal` runs this on the *same* event loop the bridge task runs
    on (both driven by the lifespan's portal), which a bare `asyncio.run()`
    here could not do since `asyncio.Event` is bound to the loop it was
    created on.
    """
    assert client.portal is not None
    subscribed = client.portal.call(app.state.ws_runtime.bridge.wait_subscribed, 5.0)
    assert subscribed, "notification Redis bridge never subscribed within 5s"


def _publish(**kwargs: object) -> UUID:
    """Sync wrapper: run `_create_and_publish_notification` on its own event
    loop. `TestClient`'s WebSocket sessions run the app on a separate loop
    managed by `anyio`'s blocking portal in a background thread, so a fresh
    `asyncio.run()` here on the main test thread never collides with it —
    both only ever meet through the real Postgres/Redis they share.
    """
    return asyncio.run(_create_and_publish_notification(**kwargs))  # type: ignore[arg-type]


def _wait_for_connection_count(app: FastAPI, expected: int, *, timeout: float = 2.0) -> None:
    """Poll `connection_count` until it reaches `expected`.

    Both connect and disconnect are asynchronous from the test's point of
    view: `WebSocketTestSession.__enter__`/`close()` only confirm the
    handshake/enqueue a disconnect message on the client side — the
    server-side router coroutine (which actually calls
    `ConnectionManager.register`/`unregister`) resumes on its own schedule
    shortly after. Asserting the count immediately is a real race (passes in
    isolation, flakes under load), so every check of this count polls
    instead of asserting once.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app.state.ws_runtime.manager.connection_count == expected:
            return
        time.sleep(0.01)
    assert app.state.ws_runtime.manager.connection_count == expected


# --- Auth rejection ----------------------------------------------------------


def test_missing_token_is_rejected_without_entering_registry() -> None:
    app = create_app(_ws_settings())
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/api/v1/ws"):
            pass
        assert exc_info.value.code == 4401
        assert app.state.ws_runtime.manager.connection_count == 0


def test_invalid_token_is_rejected_without_entering_registry() -> None:
    app = create_app(_ws_settings())
    with TestClient(app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/api/v1/ws?token=not-a-real-jwt"),
        ):
            pass
        assert exc_info.value.code == 4401
        assert app.state.ws_runtime.manager.connection_count == 0


def test_expired_token_is_rejected_without_entering_registry() -> None:
    settings = _ws_settings(access_token_expires_minutes=-1)
    app = create_app(settings)
    with TestClient(app) as client:
        owner = _register(client)
        token = _login(client, email=owner["email"], password=owner["password"])
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(f"/api/v1/ws?token={token}"),
        ):
            pass
        assert exc_info.value.code == 4401
        assert app.state.ws_runtime.manager.connection_count == 0


# --- Delivery, multi-tab, reconnect ------------------------------------------


def test_multi_tab_each_connection_receives_the_notification_once() -> None:
    settings = _ws_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        _wait_bridge_subscribed(client, app)
        owner = _register(client, username=f"ws_owner_{_unique_suffix()}")
        actor = _register(client, username=f"ws_actor_{_unique_suffix()}")
        token = _login(client, email=owner["email"], password=owner["password"])

        with (
            client.websocket_connect(f"/api/v1/ws?token={token}") as tab_1,
            client.websocket_connect(f"/api/v1/ws?token={token}") as tab_2,
        ):
            _wait_for_connection_count(app, 2)

            notification_id = _publish(
                database_url=settings.database_url,
                redis_url=settings.redis_url,
                recipient_username=owner["username"],
                actor_username=actor["username"],
            )

            for ws in (tab_1, tab_2):
                raw = _call_with_timeout(ws.receive_text, timeout=5.0)
                payload = json.loads(raw)
                assert payload["type"] == "notification"
                assert payload["event"] == "follow"
                assert payload["data"]["notification_id"] == str(notification_id)


def test_reconnect_does_not_leak_connections() -> None:
    settings = _ws_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        owner = _register(client, username=f"ws_reconn_{_unique_suffix()}")
        token = _login(client, email=owner["email"], password=owner["password"])

        for _ in range(2):
            with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
                _wait_for_connection_count(app, 1)
                # Close explicitly (and wait for the app to process it) while
                # still inside the `with` block. Relying on the implicit
                # close `WebSocketTestSession.__exit__` performs instead
                # races its own immediately-following cancel-scope
                # cancellation against the app task actually consuming the
                # queued disconnect message — observed to lose that race
                # under pytest often enough to make the implicit-close form
                # of this assertion flaky.
                ws.close()
                _wait_for_connection_count(app, 0)
            # The router's `finally` already deregistered it above; a second
            # connect immediately after must not find a leftover entry.
            _wait_for_connection_count(app, 0)


def test_event_published_by_one_process_reaches_a_socket_on_another_process() -> None:
    """Two independent `FastAPI` app instances (two `ConnectionManager`s,
    two Redis `PSUBSCRIBE` bridges), both pointed at the same real Postgres
    + Redis — simulating two API workers/processes (spec §4.2: "Whichever
    worker holds that recipient's socket receives the pub/sub message").
    """
    settings = _ws_settings()
    app_a = create_app(settings)
    app_b = create_app(settings)
    with TestClient(app_a) as client_a, TestClient(app_b) as client_b:
        _wait_bridge_subscribed(client_b, app_b)
        owner = _register(client_a, username=f"ws_procb_{_unique_suffix()}")
        actor = _register(client_a, username=f"ws_proca_{_unique_suffix()}")
        token = _login(client_a, email=owner["email"], password=owner["password"])

        # Socket lives on process B; the notification is published from
        # code that only ever touches process A's app/resources.
        with client_b.websocket_connect(f"/api/v1/ws?token={token}") as ws:
            _wait_for_connection_count(app_b, 1)
            assert app_a.state.ws_runtime.manager.connection_count == 0

            notification_id = _publish(
                database_url=settings.database_url,
                redis_url=settings.redis_url,
                recipient_username=owner["username"],
                actor_username=actor["username"],
            )

            raw = _call_with_timeout(ws.receive_text, timeout=5.0)
            payload = json.loads(raw)
            assert payload["data"]["notification_id"] == str(notification_id)


def test_delivery_latency_is_within_the_two_second_budget() -> None:
    settings = _ws_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        _wait_bridge_subscribed(client, app)
        owner = _register(client, username=f"ws_latency_{_unique_suffix()}")
        actor = _register(client, username=f"ws_latency_actor_{_unique_suffix()}")
        token = _login(client, email=owner["email"], password=owner["password"])

        with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
            start = time.monotonic()
            _publish(
                database_url=settings.database_url,
                redis_url=settings.redis_url,
                recipient_username=owner["username"],
                actor_username=actor["username"],
            )
            _call_with_timeout(ws.receive_text, timeout=5.0)
            elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"delivery took {elapsed:.3f}s, budget is 2s"


# --- Heartbeat / reaping -------------------------------------------------------


def test_idle_connection_is_reaped_within_the_heartbeat_timeout() -> None:
    # Generous enough that one slow scheduler tick (this suite runs under
    # coverage instrumentation, alongside 150+ other tests) can't make the
    # reaper's very first sweep already exceed the timeout outright — see
    # the loop below, which tolerates that outcome too, but a timeout this
    # tight made it the *common* case rather than a rare edge case.
    settings = _ws_settings(
        ws_heartbeat_interval_seconds=0.1,
        ws_heartbeat_timeout_seconds=0.4,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        owner = _register(client, username=f"ws_heartbeat_{_unique_suffix()}")
        token = _login(client, email=owner["email"], password=owner["password"])

        with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
            # Never sends a pong: the connection has no inbound activity
            # after the initial handshake, so `last_seen` never advances.
            # Zero or more `{"type": "ping"}` frames may arrive first
            # (however many sweeps land before the timeout is exceeded —
            # scheduler jitter means that count isn't deterministic), then
            # the reap closes the socket with code 4408. Only the eventual
            # reap is asserted; ping frames along the way are drained but
            # not required.
            with pytest.raises(WebSocketDisconnect) as exc_info:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    raw = _call_with_timeout(ws.receive_text, timeout=5.0)
                    assert json.loads(raw) == {"type": "ping"}
            assert exc_info.value.code == 4408

        assert app.state.ws_runtime.manager.connection_count == 0
