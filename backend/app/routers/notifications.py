"""`/notifications/*` list and mark-read routes (spec §6.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_current_user, get_db_session, get_redis
from app.models.user import User
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRepository
from app.schemas.notifications import (
    NotificationActor,
    NotificationItem,
    NotificationListResponse,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    PageInfo,
)
from app.services.notifications import NotificationsService

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _notifications_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> NotificationsService:
    return NotificationsService(
        NotificationRepository(session), UserRepository(session), session, redis
    )


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List the caller's notifications, newest first.",
)
async def list_notifications(
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    current_user: User = Depends(get_current_user),
    service: NotificationsService = Depends(_notifications_service),
) -> NotificationListResponse:
    page = await service.list_for_recipient(current_user, cursor=cursor, limit=limit)
    unread_count = await service.count_unread(current_user)
    return NotificationListResponse(
        data=[
            NotificationItem(
                id=entry.notification.id,
                type=entry.notification.type,
                actor=NotificationActor.model_validate(entry.actor),
                tweet_id=entry.notification.tweet_id,
                is_read=entry.notification.is_read,
                created_at=entry.notification.created_at,
            )
            for entry in page.items
        ],
        page=PageInfo(next_cursor=page.next_cursor),
        unread_count=unread_count,
    )


@router.post(
    "/read",
    response_model=NotificationMarkReadResponse,
    summary="Mark all, or a selected set, of the caller's notifications as read.",
)
async def mark_notifications_read(
    body: NotificationMarkReadRequest,
    current_user: User = Depends(get_current_user),
    service: NotificationsService = Depends(_notifications_service),
) -> NotificationMarkReadResponse:
    if body.notification_ids is None:
        marked_read = await service.mark_all_read(current_user)
    else:
        marked_read = await service.mark_selected_read(current_user, body.notification_ids)
    unread_count = await service.count_unread(current_user)
    return NotificationMarkReadResponse(marked_read=marked_read, unread_count=unread_count)
