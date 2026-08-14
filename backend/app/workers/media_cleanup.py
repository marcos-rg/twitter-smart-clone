"""Celery task: reap abandoned media uploads (TSC-MEDIA-001).

A `pending_uploads` row is created the moment a presigned URL is issued
(`MediaService.presign_batch`) but only flips to `confirmed` once the
client actually uploads the object *and* calls a confirm endpoint. Rows
that never get there — the user abandoned the upload, the tab closed
mid-upload, the client crashed before confirming — would otherwise
accumulate forever: an orphaned row in Postgres, and often an orphaned
object in the bucket (a client can `PUT` straight to a presigned URL and
never come back to confirm it).

`cleanup_abandoned_uploads` sweeps `pending_uploads` for rows still
`pending` after `Settings.media_abandoned_upload_ttl_hours`, best-effort
deletes whatever object (if any) landed at that key, and deletes the row.
It is a plain `@celery_app.task` — nothing here requires a `beat` container
to exist; `docker-compose.yml` currently runs only a `worker` (no `beat`),
per `TSC-CORE-001`'s "beat (periodic tasks) is deferred" note — so until a
`beat` service is added (out of scope here), this task runs whenever
invoked manually (`celery -A app.workers.celery_app call
app.workers.media_cleanup.cleanup_abandoned_uploads`) or via an external
cron calling that same command. `celery_app.conf.beat_schedule` registers
the intended cadence now so wiring an actual `beat` service later is a
one-line infra change, not a new task to write.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings, get_settings
from app.core.resources import build_resources
from app.core.storage import StorageError, build_storage
from app.models.base import utcnow
from app.repositories.pending_uploads import PendingUploadRepository
from app.workers.celery_app import celery_app

logger = structlog.get_logger("app.workers.media_cleanup")


async def _cleanup_abandoned_uploads(settings: Settings) -> int:
    """Delete every `pending_uploads` row (and its object, if any) that has
    been `pending` for longer than `media_abandoned_upload_ttl_hours`.
    Returns the number of rows reaped.
    """
    # A dedicated engine/S3 client rather than the API process's shared
    # `AppResources`: this runs in the `worker` container/process, which
    # has no FastAPI `app.state` to read them from.
    resources = await build_resources(settings)
    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    storage = build_storage(resources)
    older_than = utcnow() - timedelta(hours=settings.media_abandoned_upload_ttl_hours)

    reaped = 0
    try:
        async with sessionmaker() as session:
            repo = PendingUploadRepository(session)
            abandoned = await repo.list_abandoned(older_than=older_than)
            for row in abandoned:
                try:
                    await storage.delete_object(row.s3_key)
                except StorageError:
                    # Best-effort: the row is still stale regardless of
                    # whether the object ever existed or storage is
                    # temporarily unavailable — log and still drop the row
                    # rather than leaving it to be retried forever.
                    await logger.awarning(
                        "media_cleanup_delete_object_failed", key=row.s3_key, exc_info=True
                    )
                await repo.delete(row)
                reaped += 1
            await session.commit()
    finally:
        await resources.aclose()
        await engine.dispose()

    await logger.ainfo("media_cleanup_reaped", count=reaped)
    return reaped


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.media_cleanup.cleanup_abandoned_uploads"
)
def cleanup_abandoned_uploads() -> int:
    """Sync Celery entry point wrapping the async cleanup routine."""
    return asyncio.run(_cleanup_abandoned_uploads(get_settings()))
