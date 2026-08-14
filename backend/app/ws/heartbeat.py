"""Heartbeat / idle-socket reaping.

Every `ws_heartbeat_interval_seconds`, this:

1. Sends an application-level `{"type": "ping"}` text frame to every
   currently-registered connection (the client is expected to reply
   `{"type": "pong"}`; the router's receive loop treats *any* inbound
   message, pong or otherwise, as activity — see `app.routers.ws`).
2. Closes and deregisters any connection whose `last_seen` is older than
   `ws_heartbeat_timeout_seconds` — a socket that stopped acknowledging
   without a clean TCP close (e.g. the client's machine slept or lost
   network) would otherwise sit in the registry forever, still "receiving"
   fanned-out messages into a dead pipe.

Reconnect contract (documented here, referenced by `docs/`): a client that
misses one heartbeat window is not dropped — only a connection silent for a
full `ws_heartbeat_timeout_seconds` (by default, longer than one interval)
is reaped, giving one ping cycle of slack for a slow client before it's
considered dead.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import structlog

from app.ws.manager import ConnectionManager

logger = structlog.get_logger("app.ws.heartbeat")

_PING_FRAME = '{"type": "ping"}'


class HeartbeatReaper:
    """Background sweep that pings live connections and reaps dead ones."""

    def __init__(
        self,
        manager: ConnectionManager,
        *,
        interval_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self._manager = manager
        self._interval = interval_seconds
        self._timeout = timeout_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="ws-heartbeat-reaper")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                await self._sweep()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the reaper loop must never crash the process
            await logger.aerror("ws_heartbeat_loop_failed", exc_info=True)

    async def _sweep(self) -> None:
        now = time.monotonic()
        for connection in self._manager.all_connections():
            if now - connection.last_seen > self._timeout:
                await logger.ainfo(
                    "ws_connection_reaped",
                    user_id=str(connection.user_id),
                    connection_id=connection.id,
                    idle_seconds=now - connection.last_seen,
                )
                self._manager.unregister(connection.user_id, connection.id)
                with contextlib.suppress(Exception):
                    await connection.websocket.close(code=4408)  # 4408: app-defined "idle timeout"
                continue
            try:
                await connection.websocket.send_text(_PING_FRAME)
            except Exception:  # noqa: BLE001 - a failed ping deregisters like any failed send
                self._manager.unregister(connection.user_id, connection.id)
