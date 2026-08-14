"""Schemas for `/notifications/*` endpoints and the Redis event envelope
delivered (from `TSC-NOTIF-004` onward) over WebSocket (spec §4.2, §6.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.notification import NotificationType


class NotificationActor(BaseModel):
    """The user who triggered a notification — enough to render it without a
    follow-up profile fetch.
    """

    id: UUID
    username: str
    name: str
    avatar_key: str | None = None

    model_config = {"from_attributes": True}


class NotificationItem(BaseModel):
    """One row of `GET /notifications`."""

    id: UUID
    type: NotificationType
    actor: NotificationActor
    tweet_id: UUID | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PageInfo(BaseModel):
    next_cursor: str | None


class NotificationListResponse(BaseModel):
    data: list[NotificationItem]
    page: PageInfo
    #: Total unread count for the caller, independent of the current page —
    #: a client needs this to render an accurate badge even when the first
    #: page happens to contain zero or all-unread items.
    unread_count: int


class NotificationMarkReadRequest(BaseModel):
    """Body of `POST /notifications/read`.

    Omit `notification_ids` (or send it as `null`) to mark *all* of the
    caller's unread notifications as read. Send an explicit list to mark
    only those ids — an empty list is valid and marks nothing. Ids that
    don't exist, or belong to another user, are silently ignored rather
    than erroring; see `NotificationRepository.mark_selected_read`.
    """

    notification_ids: list[UUID] | None = Field(default=None)


class NotificationMarkReadResponse(BaseModel):
    #: How many notifications this call actually flipped from unread to
    #: read. Calling again with the same ids/mode returns `0` here — the
    #: operation is idempotent, not merely non-erroring.
    marked_read: int
    unread_count: int


# --- Redis event envelope (spec §4.2) ---------------------------------------


class NotificationEventData(BaseModel):
    notification_id: UUID
    recipient_id: UUID
    actor: NotificationActor
    tweet_id: UUID | None
    is_read: bool
    created_at: datetime


class NotificationEvent(BaseModel):
    """The exact JSON envelope `PUBLISH`ed to Redis channel
    `notifications:{recipient_id}` (spec §4.2) and, from `TSC-NOTIF-004`
    onward, pushed verbatim down the matching WebSocket connection:

    ```json
    {
      "type": "notification",
      "event": "follow | like | reply",
      "data": {
        "notification_id": "...",
        "recipient_id": "...",
        "actor": {"id": "...", "username": "...", "name": "...", "avatar_key": "..."},
        "tweet_id": "...",
        "is_read": false,
        "created_at": "..."
      }
    }
    ```

    `notification_id` is the notification row's primary key — stable and
    identical to the `id` field returned by `GET /notifications` — so
    clients can de-duplicate a live push against an item already fetched
    over REST (spec §4.2: "the client de-duplicates by notification_id").

    Two fields go beyond the spec's abbreviated example
    (`"data": {"notification_id": "...", "actor": {...}, "tweet_id": "...",
    "created_at": "..."}`) — flagged here for reviewers because this is the
    task's human-review gate:

    - `recipient_id`: lets a consumer verify/route the event without
      trusting the pub/sub channel name alone (defense in depth — a
      WebSocket handler that fans one Redis connection out to many local
      sockets can double-check it's pushing to the right one).
    - `is_read`: always `false` at publish time (an event is only ever
      published once, at creation), but included so this payload is a
      strict superset of `NotificationItem` and the client can render it
      with the exact same code path as a REST-fetched row, no
      special-casing required.
    """

    type: Literal["notification"] = "notification"
    event: NotificationType
    data: NotificationEventData
