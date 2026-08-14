"""Object-storage abstraction over the MinIO/S3-compatible client in
`app.core.resources.AppResources` (spec §8.4: media upload flow).

Everything media-upload code needs from S3/MinIO goes through this module:
building safe object keys, issuing presigned `PUT` URLs, and reading back
object metadata to verify an upload actually happened. Callers (services)
never touch `aioboto3`/`botocore` directly, so `app.services.media` stays
testable against a fake/mock implementing this same surface and swappable to
a different S3-compatible provider without touching business logic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from botocore.exceptions import ClientError

from app.core.resources import AppResources, S3Client
from app.models.pending_upload import MediaPurpose

#: Content-types this app accepts anywhere media is uploaded (spec §8.4:
#: "image/png|jpeg|webp only"). Kept in sync with, and re-exported from,
#: `app.models.tweet_media.ALLOWED_CONTENT_TYPES` (the source of truth for
#: what a *confirmed* `tweet_media` row may contain) rather than duplicated,
#: since avatars are constrained to exactly the same set.
from app.models.tweet_media import ALLOWED_CONTENT_TYPES

_EXTENSIONS_BY_CONTENT_TYPE: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class UnsupportedContentTypeError(ValueError):
    """Raised for a content-type outside `ALLOWED_CONTENT_TYPES`."""


def build_object_key(*, user_id: UUID, purpose: MediaPurpose, content_type: str) -> str:
    """A randomized, user-scoped object key: `{purpose}/{user_id}/{uuid4}{ext}`.

    Never derived from client-supplied filenames/paths — the only client
    input reflected in the key is the (already-validated) content-type's
    extension — so there is no path-traversal surface (no `..`, no
    attacker-chosen segments) and no way to guess or collide with another
    upload's key (a fresh `uuid4` every call). Scoping the key under the
    owning user's id, rather than relying on the key alone, is what makes
    "confirming a key owned by another user" a checkable condition in
    `PendingUpload` (see that model's docstring) — the key's prefix is
    informational for humans browsing the bucket, not itself a trust
    boundary the confirm path relies on.
    """
    try:
        extension = _EXTENSIONS_BY_CONTENT_TYPE[content_type]
    except KeyError as exc:
        raise UnsupportedContentTypeError(content_type) from exc
    # Guard against `_EXTENSIONS_BY_CONTENT_TYPE` and `ALLOWED_CONTENT_TYPES`
    # ever drifting apart (both must list exactly the supported types).
    assert content_type in ALLOWED_CONTENT_TYPES  # noqa: S101
    return f"{purpose.value}/{user_id}/{uuid.uuid4().hex}{extension}"


@dataclass(frozen=True)
class ObjectMetadata:
    """The subset of S3 `HeadObject` output the confirm path checks."""

    content_type: str
    content_length: int


class StorageError(Exception):
    """Wraps any unexpected storage-backend failure (network error, MinIO
    down, credentials rejected, ...) so callers depend on one exception type
    instead of `botocore`'s. Distinguished from `ObjectStorage.head_object`
    returning `None` (the mundane, expected "object doesn't exist yet" case,
    e.g. the client never finished the `PUT`).
    """


class SupportsObjectStorage(Protocol):
    """The surface `app.services.media.MediaService` depends on — real
    `ObjectStorage` or a test double.
    """

    async def presign_put(self, *, key: str, content_type: str, expires_seconds: int) -> str: ...

    async def head_object(self, key: str) -> ObjectMetadata | None: ...

    async def delete_object(self, key: str) -> None: ...


class ObjectStorage:
    """`SupportsObjectStorage` backed by the app's shared `aioboto3` S3
    client (`AppResources.s3_client`), pointed at MinIO in dev/test and
    AWS S3 in prod (spec §5.3: "S3-compatible").
    """

    def __init__(self, client: S3Client, *, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def presign_put(self, *, key: str, content_type: str, expires_seconds: int) -> str:
        """A presigned `PUT` URL the client uploads directly to (spec §8.4
        step 2-3) — the API container's request body never carries image
        bytes. `ContentType` is bound into the signature, so the client
        can't swap in a different content-type at upload time without
        invalidating the signature (S3/MinIO rejects the `PUT` outright);
        `confirm`'s metadata check (comparing the declared vs. actual
        content-type) is a second, independent line of defense on top of
        that, not the only one.
        """
        try:
            url = await self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=expires_seconds,
            )
        except ClientError as exc:  # pragma: no cover - defensive; signing is local
            raise StorageError(f"Failed to presign upload for {key!r}.") from exc
        return str(url)

    async def head_object(self, key: str) -> ObjectMetadata | None:
        """The object's actual content-type/size, or `None` if it doesn't
        exist (spec §8.4: "server verifies the object exists").
        """
        try:
            response = await self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise StorageError(f"Failed to read metadata for {key!r}.") from exc
        return ObjectMetadata(
            content_type=response.get("ContentType", ""),
            content_length=int(response.get("ContentLength", 0)),
        )

    async def delete_object(self, key: str) -> None:
        """Best-effort delete (cleanup of abandoned/rejected uploads).
        Deleting a key that doesn't exist is not an error in S3's API.
        """
        try:
            await self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"Failed to delete {key!r}.") from exc


def build_storage(resources: AppResources) -> ObjectStorage:
    """The `ObjectStorage` bound to this process's shared S3 client/bucket."""
    return ObjectStorage(resources.s3_client, bucket=resources.minio_bucket)
