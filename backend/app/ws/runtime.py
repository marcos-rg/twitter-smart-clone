"""Process-wide WebSocket runtime: the `ConnectionManager`, the Redis
fan-out bridge, and the heartbeat reaper, composed and lifecycle-managed
together. One instance lives on `app.state.ws_runtime` for the lifetime of
the process (spec §4.2/§4.1: "API (FastAPI): stateless HTTP + WebSocket app;
runs as multiple Uvicorn workers").

Kept separate from `app.core.resources.AppResources` (DB/Redis/S3 client
handles) because this runtime is layered *on top of* those resources rather
than being one itself — it needs `resources.redis` to already exist before
it can start.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.resources import AppResources
from app.ws.heartbeat import HeartbeatReaper
from app.ws.manager import ConnectionManager
from app.ws.redis_bridge import NotificationRedisBridge


@dataclass
class WebSocketRuntime:
    manager: ConnectionManager
    bridge: NotificationRedisBridge
    heartbeat: HeartbeatReaper

    async def start(self) -> None:
        await self.bridge.start()
        await self.heartbeat.start()

    async def stop(self) -> None:
        await self.heartbeat.stop()
        await self.bridge.stop()


def build_ws_runtime(resources: AppResources, settings: Settings) -> WebSocketRuntime:
    """Construct (but do not start) the runtime for one process."""
    manager = ConnectionManager()
    bridge = NotificationRedisBridge(resources.redis, manager)
    heartbeat = HeartbeatReaper(
        manager,
        interval_seconds=settings.ws_heartbeat_interval_seconds,
        timeout_seconds=settings.ws_heartbeat_timeout_seconds,
    )
    return WebSocketRuntime(manager=manager, bridge=bridge, heartbeat=heartbeat)
