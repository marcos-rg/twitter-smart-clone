"""`/media/*` presign + confirm routes (spec §6.3, §8.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.deps import get_current_user, get_db_session, get_resources, get_settings_dep
from app.core.resources import AppResources
from app.core.storage import build_storage
from app.models.user import User
from app.repositories.pending_uploads import PendingUploadRepository
from app.schemas.media import ConfirmRequest, ConfirmResponse, PresignRequest, PresignResponse
from app.services.media import MediaLimits, MediaService

router = APIRouter(prefix="/api/v1/media", tags=["media"])


def _media_service(
    session: AsyncSession = Depends(get_db_session),
    resources: AppResources = Depends(get_resources),
    settings: Settings = Depends(get_settings_dep),
) -> MediaService:
    return MediaService(
        PendingUploadRepository(session),
        build_storage(resources),
        MediaLimits(
            max_image_bytes=settings.media_max_image_bytes,
            max_tweet_images=settings.media_max_tweet_images,
            presign_expires_seconds=settings.media_presign_expires_seconds,
        ),
    )


@router.post(
    "/presign",
    response_model=PresignResponse,
    summary="Get presigned S3/MinIO upload URLs for one or more images.",
)
async def presign_media(
    body: PresignRequest,
    current_user: User = Depends(get_current_user),
    service: MediaService = Depends(_media_service),
) -> PresignResponse:
    uploads = await service.presign_batch(current_user, purpose=body.purpose, files=body.files)
    return PresignResponse(uploads=uploads)


@router.post(
    "/confirm",
    response_model=ConfirmResponse,
    summary="Confirm previously presigned keys were uploaded (verifies object existence).",
)
async def confirm_media(
    body: ConfirmRequest,
    current_user: User = Depends(get_current_user),
    service: MediaService = Depends(_media_service),
) -> ConfirmResponse:
    media = await service.confirm_keys(current_user, purpose=body.purpose, keys=body.keys)
    return ConfirmResponse(media=media)
