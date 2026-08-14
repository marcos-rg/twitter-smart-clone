"""Redis pub/sub → local `ConnectionManager` bridge (spec §4.2 point 3/4):
"Server subscribes the process to the Redis channel `notifications:{user_id}`
... Whichever worker holds that recipient's socket receives the pub/sub
message and pushes it down the WebSocket."

Rather than `SUBSCRIBE`/`UNSUBSCRIBE`ing a per-recipient channel each time a
socket connects/disconnects (spec's first option), this process opens a
single long-lived `PSUBSCRIBE notifications:*` (spec's documented
alternative: "a single `notifications` channel with user routing") for its
entire lifetime. That means:

- Exactly one Redis connection per API process for this purpose, regardless
  of how many users/connections it currently holds — no per-connection Redis
  subscribe/unsubscribe bookkeeping that could leak on a bad reconnect.
- A reconnect (unregister + re-register in `ConnectionManager`) touches only
  local, in-process state; the Redis-side subscription is untouched, so
  nothing there can leak either.
- Any process can `PUBLISH` (via `app.services.notification_publisher`) and
  every process routes the message locally by parsing the recipient id back
  out of the channel name, matching `NotificationEventData.recipient_id` as
  a defense-in-depth cross-check.

**Startup is lazy, like every other resource in `app.core.resources`**
("Connections are lazy: this does not block on the dependencies actually
being reachable, so the app can still start ... even if a dependency is
temporarily down"). `start()` only launches the background task; the task
itself retries `PSUBSCRIBE` with backoff until it succeeds, so a Redis
outage at process boot never fails app startup (and, by extension, never
fails `/readyz`, which reports Redis health independently) — it just delays
live delivery until Redis comes back, exactly like the readiness checks in
`app.core.resources` already tolerate.
"""

from __future__ import annotations

import asyncio
import contextlib
from uuid import UUID

import structlog
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.ws.manager import ConnectionManager

logger = structlog.get_logger("app.ws.redis_bridge")

#: Matches `notification_channel()` in `app.services.notification_publisher`
#: (`notifications:{recipient_id}`) for every recipient at once.
_CHANNEL_PATTERN = "notifications:*"

#: Backoff between reconnect attempts after `PSUBSCRIBE` or the listen loop
#: itself fails (Redis unreachable/restarting).
_RECONNECT_DELAY_SECONDS = 1.0


class NotificationRedisBridge:
    """Owns one `PSUBSCRIBE notifications:*` Redis connection for the process
    and forwards each message to the local `ConnectionManager`.
    """

    def __init__(self, redis: Redis, manager: ConnectionManager) -> None:
        self._redis = redis
        self._manager = manager
        self._pubsub: PubSub | None = None
        self._task: asyncio.Task[None] | None = None
        #: Set for as long as `PSUBSCRIBE` is currently active; cleared on
        #: disconnect and re-set on reconnect. `wait_subscribed` lets a
        #: caller (tests; a future readiness probe) deterministically wait
        #: for "this process is actually receiving Redis pub/sub" instead of
        #: racing a fixed sleep against the retry loop above.
        self._subscribed = asyncio.Event()

    async def start(self) -> None:
        """Start the background forwarding loop. Idempotent — calling twice
        without an intervening `stop()` is a no-op. Never raises: the loop
        itself retries the initial `PSUBSCRIBE` until Redis is reachable.
        """
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_forever(), name="notification-redis-bridge")

    async def wait_subscribed(self, timeout: float = 5.0) -> bool:
        """Block until the process is actively subscribed to Redis, up to
        `timeout` seconds. Returns whether it became subscribed in time.
        """
        try:
            async with asyncio.timeout(timeout):
                await self._subscribed.wait()
            return True
        except TimeoutError:
            return False

    async def stop(self) -> None:
        """Cancel the forwarding loop and release the Redis subscription.
        Safe to call even if `start()` was never called.
        """
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.punsubscribe(_CHANNEL_PATTERN)
                await self._pubsub.aclose()  # type: ignore[no-untyped-call]
            self._pubsub = None
        self._subscribed.clear()

    async def _run_forever(self) -> None:
        """(Re)connect and drain messages until cancelled. A failure at any
        point (initial subscribe or mid-stream) is logged and retried after
        `_RECONNECT_DELAY_SECONDS` rather than propagating — this task must
        outlive individual Redis blips for the whole process's lifetime.
        """
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.psubscribe(_CHANNEL_PATTERN)
                self._pubsub = pubsub
                self._subscribed.set()
                await logger.ainfo("ws_redis_bridge_subscribed", pattern=_CHANNEL_PATTERN)
                async for message in pubsub.listen():
                    if message["type"] != "pmessage":
                        continue
                    await self._forward(message["channel"], message["data"])
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - reconnect-and-retry, never crash the process
                await logger.awarning("ws_redis_bridge_disconnected", exc_info=True)
                self._pubsub = None
                self._subscribed.clear()
                await asyncio.sleep(_RECONNECT_DELAY_SECONDS)

    async def _forward(self, channel: str, payload: str) -> None:
        _, _, raw_user_id = channel.partition(":")
        try:
            user_id = UUID(raw_user_id)
        except ValueError:
            await logger.awarning("ws_redis_bridge_bad_channel", channel=channel)
            return
        await self._manager.send_to_user(user_id, payload)
