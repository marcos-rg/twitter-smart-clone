"""Business rules for direct-to-S3/MinIO media uploads (spec §8.4).

Presign issues a time-limited `PUT` URL and records a `PendingUpload` row
scoped to the requesting user; confirm re-checks everything server-side
(ownership, the object's *actual* metadata vs. what was declared, counts)
before treating an upload as real. Nothing here trusts the client past the
presign step — a client can request a presigned URL and then upload
anything (or nothing) to it, so confirm is where the server actually
verifies what landed in storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.core.errors import AppError
from app.core.storage import SupportsObjectStorage, build_object_key
from app.models.base import utcnow
from app.models.pending_upload import MediaPurpose, PendingUpload, PendingUploadStatus
from app.models.tweet_media import ALLOWED_CONTENT_TYPES
from app.models.user import User
from app.repositories.pending_uploads import PendingUploadRepository
from app.schemas.media import (
    ConfirmedMedia,
    PresignedUpload,
    PresignFileRequest,
)


class UnsupportedMediaTypeError(AppError):
    status_code = 400
    code = "unsupported_media_type"

    def __init__(self, content_type: str) -> None:
        super().__init__(f"Unsupported content type: {content_type!r}.")


class MediaTooLargeError(AppError):
    status_code = 400
    code = "media_too_large"

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"File exceeds the maximum allowed size of {max_bytes} bytes.")


class TooManyMediaFilesError(AppError):
    status_code = 400
    code = "too_many_media_files"

    def __init__(self, max_files: int) -> None:
        super().__init__(f"At most {max_files} file(s) are allowed for this purpose.")


class MediaNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, key: str) -> None:
        super().__init__(f"No pending upload found for key {key!r}.")


class MediaForbiddenError(AppError):
    status_code = 403
    code = "forbidden"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} does not belong to the current user.")


class MediaPurposeMismatchError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} was not presigned for this purpose.")


class MediaObjectMissingError(AppError):
    """The presigned key exists, but nothing was ever uploaded to it (spec:
    "server verifies the object exists").
    """

    status_code = 400
    code = "media_object_missing"

    def __init__(self, key: str) -> None:
        super().__init__(f"No object was found in storage for key {key!r}.")


class MediaMetadataMismatchError(AppError):
    """The uploaded object's actual content-type/size doesn't match what was
    declared at presign time — the client swapped in a different file
    after getting the presigned URL.
    """

    status_code = 400
    code = "media_metadata_mismatch"

    def __init__(self, key: str) -> None:
        super().__init__(f"Uploaded object for key {key!r} does not match the declared upload.")


class MediaAlreadyConfirmedError(AppError):
    status_code = 409
    code = "conflict"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} was already confirmed.")


@dataclass(frozen=True)
class MediaLimits:
    max_image_bytes: int
    max_tweet_images: int
    presign_expires_seconds: int


class MediaService:
    def __init__(
        self,
        pending_uploads: PendingUploadRepository,
        storage: SupportsObjectStorage,
        limits: MediaLimits,
    ) -> None:
        self.pending_uploads = pending_uploads
        self.storage = storage
        self.limits = limits

    def _max_files_for(self, purpose: MediaPurpose) -> int:
        return 1 if purpose is MediaPurpose.AVATAR else self.limits.max_tweet_images

    def _validate_file(self, file: PresignFileRequest) -> None:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedMediaTypeError(file.content_type)
        if file.size_bytes > self.limits.max_image_bytes:
            raise MediaTooLargeError(self.limits.max_image_bytes)

    async def presign_batch(
        self, user: User, *, purpose: MediaPurpose, files: list[PresignFileRequest]
    ) -> list[PresignedUpload]:
        """Validate and presign every file in one batch (spec §8.4 steps
        1-2). Rejects the whole batch (no partial presigns) if any file is
        invalid or the batch exceeds the per-purpose count limit.
        """
        max_files = self._max_files_for(purpose)
        if len(files) > max_files:
            raise TooManyMediaFilesError(max_files)
        for file in files:
            self._validate_file(file)

        now = utcnow()
        expires_at = now + timedelta(seconds=self.limits.presign_expires_seconds)
        uploads: list[PresignedUpload] = []
        for file in files:
            key = build_object_key(user_id=user.id, purpose=purpose, content_type=file.content_type)
            upload_url = await self.storage.presign_put(
                key=key,
                content_type=file.content_type,
                expires_seconds=self.limits.presign_expires_seconds,
            )
            await self.pending_uploads.add(
                PendingUpload(
                    user_id=user.id,
                    purpose=purpose,
                    s3_key=key,
                    content_type=file.content_type,
                    size_bytes=file.size_bytes,
                    presign_expires_at=expires_at,
                )
            )
            uploads.append(
                PresignedUpload(
                    key=key,
                    upload_url=upload_url,
                    content_type=file.content_type,
                    expires_at=expires_at,
                )
            )
        return uploads

    async def confirm_keys(
        self, user: User, *, purpose: MediaPurpose, keys: list[str]
    ) -> list[ConfirmedMedia]:
        """Re-verify and confirm every key in one batch (spec §8.4 step 4).

        Each key must: have been presigned (a `PendingUpload` row exists),
        belong to `user`, match `purpose`, not already be confirmed, and
        have a real object in storage whose actual content-type/size match
        what was declared at presign time. Any failure rejects the whole
        batch — a tweet's images are confirmed atomically, not partially.
        """
        max_files = self._max_files_for(purpose)
        if len(keys) > max_files:
            raise TooManyMediaFilesError(max_files)

        pending_rows: list[PendingUpload] = []
        for key in keys:
            pending = await self.pending_uploads.get_by_key(key)
            if pending is None:
                raise MediaNotFoundError(key)
            if pending.user_id != user.id:
                raise MediaForbiddenError(key)
            if pending.purpose is not purpose:
                raise MediaPurposeMismatchError(key)
            if pending.status is PendingUploadStatus.CONFIRMED:
                raise MediaAlreadyConfirmedError(key)
            pending_rows.append(pending)

        confirmed: list[ConfirmedMedia] = []
        for pending in pending_rows:
            metadata = await self.storage.head_object(pending.s3_key)
            if metadata is None:
                raise MediaObjectMissingError(pending.s3_key)
            if (
                metadata.content_type != pending.content_type
                or metadata.content_length != pending.size_bytes
                or metadata.content_length > self.limits.max_image_bytes
            ):
                raise MediaMetadataMismatchError(pending.s3_key)

            pending.status = PendingUploadStatus.CONFIRMED
            pending.confirmed_at = utcnow()
            self.pending_uploads.session.add(pending)
            confirmed.append(
                ConfirmedMedia(
                    key=pending.s3_key,
                    content_type=pending.content_type,
                    size_bytes=pending.size_bytes,
                )
            )
        await self.pending_uploads.session.flush()
        return confirmed

    async def confirm_avatar(self, user: User, *, key: str) -> ConfirmedMedia:
        """Confirm a single avatar upload and persist it onto `user`
        (spec: "Confirming an owned avatar updates the authenticated user's
        profile").
        """
        [confirmed] = await self.confirm_keys(user, purpose=MediaPurpose.AVATAR, keys=[key])
        user.avatar_key = confirmed.key
        user.updated_at = utcnow()
        self.pending_uploads.session.add(user)
        await self.pending_uploads.session.flush()
        return confirmed
