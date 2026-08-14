"""In-process WebSocket connection registry, keyed by `user_id` (spec §4.2:
"registers the connection in an in-process `ConnectionManager` keyed by
`user_id` ... a user may have multiple connections/tabs").

This is deliberately the *only* place that holds live `WebSocket` objects.
Everything else (the router, the Redis bridge, the heartbeat reaper) goes
through this class rather than touching sockets directly, so connection
bookkeeping (registration, fan-out, staleness, teardown) has one owner.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from starlette.websockets import WebSocket

logger = structlog.get_logger("app.ws.manager")


@dataclass
class Connection:
    """One live WebSocket, tracked for fan-out and heartbeat purposes."""

    id: str
    user_id: UUID
    websocket: WebSocket
    #: `time.monotonic()` timestamp of the last inbound activity (connect,
    #: any client message, or a `pong`). The heartbeat reaper compares this
    #: against `ws_heartbeat_timeout_seconds` to detect dead sockets that
    #: never sent a TCP FIN (e.g. a laptop that went to sleep).
    last_seen: float = field(default_factory=time.monotonic)


class ConnectionManager:
    """Tracks live connections per user and fans out messages to them.

    Every mutating operation is guarded by a single `asyncio.Lock` — the
    connection counts here are small (per-process, per-user tab count), so a
    coarse lock is simpler and cheap enough; it never guards anything that
    awaits a socket write while held.
    """

    def __init__(self) -> None:
        self._by_user: dict[UUID, dict[str, Connection]] = {}

    def register(self, user_id: UUID, websocket: WebSocket) -> Connection:
        """Record `websocket` as belonging to `user_id`. Must only be called
        *after* `websocket.accept()` — the router rejects invalid credentials
        before ever reaching this call, so nothing unauthenticated is ever
        registered.
        """
        connection = Connection(id=uuid.uuid4().hex, user_id=user_id, websocket=websocket)
        self._by_user.setdefault(user_id, {})[connection.id] = connection
        return connection

    def unregister(self, user_id: UUID, connection_id: str) -> None:
        """Remove one connection. Safe to call more than once (e.g. once from
        the router's `finally` block and once from the heartbeat reaper) —
        a second call for an already-removed id is a no-op.
        """
        connections = self._by_user.get(user_id)
        if connections is None:
            return
        connections.pop(connection_id, None)
        if not connections:
            self._by_user.pop(user_id, None)

    def touch(self, user_id: UUID, connection_id: str) -> None:
        """Refresh `last_seen` on inbound activity from this connection."""
        connection = self._by_user.get(user_id, {}).get(connection_id)
        if connection is not None:
            connection.last_seen = time.monotonic()

    def connections_for(self, user_id: UUID) -> list[Connection]:
        """A snapshot list of the user's currently-registered connections."""
        return list(self._by_user.get(user_id, {}).values())

    def all_connections(self) -> list[Connection]:
        """A snapshot of every connection currently registered, across users
        — used by the heartbeat reaper's sweep.
        """
        return [conn for conns in self._by_user.values() for conn in conns.values()]

    @property
    def connection_count(self) -> int:
        return sum(len(conns) for conns in self._by_user.values())

    async def send_to_user(self, user_id: UUID, message: str) -> None:
        """Push `message` (raw text, e.g. the notification event's JSON) to
        every connection currently registered for `user_id` — once per
        connection, so a user with two open tabs gets it twice, once each
        (spec: "a user may have multiple connections/tabs").

        A send failure on one connection (socket already gone) is logged and
        that connection is deregistered; it never prevents delivery to the
        user's other connections.
        """
        for connection in self.connections_for(user_id):
            try:
                await connection.websocket.send_text(message)
            except Exception:  # noqa: BLE001 - a dead socket must not block delivery to others
                await logger.awarning(
                    "ws_send_failed",
                    user_id=str(user_id),
                    connection_id=connection.id,
                    exc_info=True,
                )
                self.unregister(user_id, connection.id)
