"""Business rules for the notification resource: persistence, cursor listing,
mark-read, and post-commit Redis publication (spec §4.2, §8.5).

Trigger wiring — actually *calling* `create_notification` when a follow,
like, or reply happens — belongs to the tasks that own those actions
(`TSC-SOC-*`, `TSC-LIKE-*`, `TSC-TWEET-*`); this service only owns the
notification resource itself, so it can be built and tested ahead of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.core.outbox import queue_post_commit
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.repositories.notifications import NotificationRepository
from app.repositories.pagination import Cursor, InvalidCursorError, Page, decode_cursor
from app.repositories.users import UserRepository
from app.schemas.notifications import NotificationActor, NotificationEvent, NotificationEventData
from app.services.notification_publisher import publish_notification_event


class InvalidPaginationCursorError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self) -> None:
        super().__init__("Invalid pagination cursor.")


@dataclass(frozen=True)
class NotificationWithActor:
    """One notification paired with the `User` who triggered it — the shape
    `list_for_recipient` returns so the router can build `NotificationItem`
    without a second round trip per row.
    """

    notification: Notification
    actor: User


class NotificationsService:
    def __init__(
        self,
        notifications: NotificationRepository,
        users: UserRepository,
        session: AsyncSession,
        redis: Redis,
    ) -> None:
        self.notifications = notifications
        self.users = users
        self.session = session
        self.redis = redis

    async def create_notification(
        self,
        *,
        recipient_id: UUID,
        actor: User,
        type_: NotificationType,
        tweet_id: UUID | None,
    ) -> Notification | None:
        """Persist one notification row and queue its Redis publish to run
        once this request's transaction commits (see `app.core.outbox`).

        No-ops (returns `None`, nothing persisted or queued) when
        `recipient_id == actor.id`: a user is never notified of their own
        action (e.g. liking or replying to their own tweet). This is a
        defensive guard in the shared resource so trigger-wiring tasks don't
        each need to re-implement the check.
        """
        if recipient_id == actor.id:
            return None

        notification = await self.notifications.add(
            Notification(
                recipient_id=recipient_id,
                actor_id=actor.id,
                type=type_,
                tweet_id=tweet_id,
            )
        )

        event = NotificationEvent(
            event=type_,
            data=NotificationEventData(
                notification_id=notification.id,
                recipient_id=notification.recipient_id,
                actor=NotificationActor.model_validate(actor),
                tweet_id=notification.tweet_id,
                is_read=notification.is_read,
                created_at=notification.created_at,
            ),
        )

        async def _publish() -> None:
            await publish_notification_event(self.redis, event)

        queue_post_commit(self.session, _publish)
        return notification

    async def list_for_recipient(
        self, recipient: User, *, cursor: str | None, limit: int | None
    ) -> Page[NotificationWithActor]:
        """`recipient`'s notifications, newest first, each paired with its
        actor. Scoped to `recipient.id` at the repository query level — a
        caller can never see another user's notifications through this
        method, by construction, not by a post-hoc filter.
        """
        decoded_cursor = self._decode_cursor(cursor)
        page = await self.notifications.list_for_recipient(
            recipient.id, cursor=decoded_cursor, limit=limit
        )
        if not page.items:
            return Page(items=[], next_cursor=page.next_cursor)

        actor_ids = {notification.actor_id for notification in page.items}
        actors_by_id = {actor.id: actor for actor in await self.users.get_many(list(actor_ids))}
        items = [
            NotificationWithActor(
                notification=notification, actor=actors_by_id[notification.actor_id]
            )
            for notification in page.items
        ]
        return Page(items=items, next_cursor=page.next_cursor)

    async def count_unread(self, recipient: User) -> int:
        return await self.notifications.count_unread(recipient.id)

    async def mark_all_read(self, recipient: User) -> int:
        """Mark every unread notification for `recipient` as read. Returns
        how many were actually flipped — `0` on a repeat call, since it's
        idempotent (spec: "Mark-selected and mark-all-read ... are
        idempotent").
        """
        return await self.notifications.mark_all_read(recipient.id)

    async def mark_selected_read(self, recipient: User, notification_ids: list[UUID]) -> int:
        """Mark the given notification ids as read, scoped to `recipient`.
        Ids that don't belong to `recipient` (or don't exist) are silently
        excluded rather than erroring. Returns how many were actually
        flipped; idempotent like `mark_all_read`.
        """
        return await self.notifications.mark_selected_read(recipient.id, notification_ids)

    @staticmethod
    def _decode_cursor(cursor: str | None) -> Cursor | None:
        if cursor is None:
            return None
        try:
            return decode_cursor(cursor)
        except InvalidCursorError as exc:
            raise InvalidPaginationCursorError() from exc
