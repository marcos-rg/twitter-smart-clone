"""`NotificationRepository` (spec §5.1: `notifications`).

`list_unread`/`count_unread` are backed by the partial index on
`(recipient_id) WHERE is_read = false` from the initial migration — cheap
even as the read/notification history grows, since the index only ever
covers the (small) unread subset.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select

from app.models.notification import Notification, NotificationType
from app.repositories.base import BaseRepository
from app.repositories.pagination import Cursor, Page, apply_keyset, build_page, clamp_limit


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def exists(
        self,
        *,
        recipient_id: UUID,
        actor_id: UUID,
        type: NotificationType,
        tweet_id: UUID | None,
    ) -> bool:
        """Whether a matching notification already exists. Used by the
        idempotent seed script to avoid inserting duplicate demo
        notifications on a second run (notifications have no natural unique
        constraint in the schema itself — the same follow/like/reply could
        legitimately notify more than once in the real app, e.g. re-follow
        after unfollow — so this is a seed-only convenience, not a
        database-level invariant).
        """
        result = await self.session.exec(
            select(Notification).where(
                Notification.recipient_id == recipient_id,
                Notification.actor_id == actor_id,
                Notification.type == type,
                (
                    Notification.tweet_id == tweet_id
                    if tweet_id is not None
                    else Notification.tweet_id.is_(None)  # type: ignore[union-attr]
                ),
            )
        )
        return result.first() is not None

    async def list_for_recipient(
        self, recipient_id: UUID, *, cursor: Cursor | None, limit: int | None
    ) -> Page[Notification]:
        """All notifications for `recipient_id`, newest first."""
        limit = clamp_limit(limit)
        stmt = apply_keyset(
            select(Notification).where(Notification.recipient_id == recipient_id),
            created_at_col=Notification.created_at,  # type: ignore[arg-type]
            id_col=Notification.id,  # type: ignore[arg-type]
            cursor=cursor,
            direction="desc",
        ).limit(limit + 1)
        result = await self.session.exec(stmt)  # type: ignore[call-overload]
        rows = list(result.all())
        return build_page(rows, limit, created_at_of=lambda n: n.created_at, id_of=lambda n: n.id)

    async def count_unread(self, recipient_id: UUID) -> int:
        result = await self.session.exec(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.is_read.is_(False),  # type: ignore[attr-defined]
            )
        )
        return int(result.one())

    async def mark_all_read(self, recipient_id: UUID) -> int:
        """Mark every currently-unread notification for `recipient_id` as
        read. Idempotent: only rows with `is_read = false` are selected, so
        a second call matches zero rows and returns `0` — it never
        "unreads" or re-touches an already-read row.
        """
        result = await self.session.exec(
            select(Notification).where(
                Notification.recipient_id == recipient_id,
                Notification.is_read.is_(False),  # type: ignore[attr-defined]
            )
        )
        rows = result.all()
        for notification in rows:
            notification.is_read = True
            self.session.add(notification)
        await self.session.flush()
        return len(rows)

    async def mark_selected_read(
        self, recipient_id: UUID, notification_ids: Sequence[UUID]
    ) -> int:
        """Mark the given notification ids as read, scoped to
        `recipient_id`.

        Ids that don't exist, or belong to a different recipient, are
        silently excluded by the `WHERE` clause rather than raising —
        callers can only ever affect their own notifications, and a
        404/403 here would let a client probe whether some other user's
        notification id exists. Only rows with `is_read = false` are
        matched, so marking the same id(s) twice updates them exactly once:
        the second call matches zero rows for ids already marked read.
        """
        if not notification_ids:
            return 0
        result = await self.session.exec(
            select(Notification).where(
                Notification.recipient_id == recipient_id,
                Notification.id.in_(notification_ids),  # type: ignore[attr-defined]
                Notification.is_read.is_(False),  # type: ignore[attr-defined]
            )
        )
        rows = result.all()
        for notification in rows:
            notification.is_read = True
            self.session.add(notification)
        await self.session.flush()
        return len(rows)
