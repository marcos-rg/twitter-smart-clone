"""Post-commit Redis publisher for the notification event envelope
(spec §4.2). This is the first pub/sub publisher in the codebase — it
defines the contract `TSC-NOTIF-004` (WebSocket delivery) and every
follow/like/reply trigger-wiring task build on:

- **Channel:** `notifications:{recipient_id}` — one channel per recipient,
  matching spec §4.2 point 3 ("Server subscribes the process to the Redis
  channel `notifications:{user_id}`"). This lets any worker `PUBLISH` and
  only the worker(s) holding that recipient's WebSocket connection need to
  receive it.
- **Payload:** the JSON-serialized `app.schemas.notifications.NotificationEvent`
  envelope, documented in full on that class.
- **Ordering:** never called directly by request-handling code. Callers
  queue it via `app.core.outbox.queue_post_commit` from inside a service
  method (see `NotificationsService.create_notification`); `get_db_session`
  drains the queue immediately after `session.commit()` succeeds. This
  guarantees the notification row is durably committed before any event
  referencing it reaches Redis, and that a rolled-back transaction
  publishes nothing at all.
- **Failure handling:** a publish failure (Redis unreachable, timeout, ...)
  is logged and swallowed, never raised. By the time this runs the
  notification row is already committed, so the recipient still sees it on
  their next `GET /notifications` fetch — losing the live push is a
  latency/availability degradation, not a correctness bug (spec §4.2:
  "at-least-once via persistence + live push ... WebSocket is a delivery
  accelerator, not the source of truth — the DB is"). Letting an exception
  escape here would also be actively harmful: this runs during FastAPI
  dependency teardown, after the response has effectively been decided, so
  it would surface to the client as a `500` for a request that already
  succeeded.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from redis.asyncio import Redis

from app.schemas.notifications import NotificationEvent

logger = structlog.get_logger("app.notifications.publisher")


def notification_channel(recipient_id: UUID) -> str:
    """The per-recipient Redis pub/sub channel name (spec §4.2)."""
    return f"notifications:{recipient_id}"


async def publish_notification_event(redis: Redis, event: NotificationEvent) -> None:
    """`PUBLISH` `event`'s JSON envelope to its recipient's channel.

    Must only be invoked after the notification row's transaction has
    committed — see the module docstring. Never raises: failures are logged
    and swallowed.
    """
    channel = notification_channel(event.data.recipient_id)
    payload = event.model_dump_json()
    try:
        await redis.publish(channel, payload)
    except Exception:  # noqa: BLE001 - publish failures degrade to "offline delivery", never a 500
        await logger.awarning(
            "notification_publish_failed",
            notification_id=str(event.data.notification_id),
            recipient_id=str(event.data.recipient_id),
            channel=channel,
            exc_info=True,
        )
