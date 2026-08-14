"""`PendingUploadRepository` (see `app.models.pending_upload`)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from app.models.pending_upload import PendingUpload, PendingUploadStatus
from app.repositories.base import BaseRepository


class PendingUploadRepository(BaseRepository[PendingUpload]):
    model = PendingUpload

    async def get_by_key(self, s3_key: str) -> PendingUpload | None:
        result = await self.session.exec(
            select(PendingUpload).where(PendingUpload.s3_key == s3_key)
        )
        return result.first()

    async def list_abandoned(
        self, *, older_than: datetime, limit: int = 500
    ) -> list[PendingUpload]:
        """Rows still `pending` and created before `older_than` — candidates
        for `app.workers.media_cleanup`.
        """
        result = await self.session.exec(
            select(PendingUpload)
            .where(
                PendingUpload.status == PendingUploadStatus.PENDING,
                PendingUpload.created_at < older_than,
            )
            .limit(limit)
        )
        return list(result.all())
