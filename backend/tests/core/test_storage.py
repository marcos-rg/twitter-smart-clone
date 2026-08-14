"""Unit tests for `app.core.storage` (TSC-MEDIA-001): object key
randomization/scoping and the S3-failure -> `StorageError` translation,
using a mocked `aioboto3`-shaped client (no real MinIO needed for these —
see `tests/test_media.py` for the real-MinIO integration path).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError

from app.core.storage import (
    ObjectStorage,
    StorageError,
    UnsupportedContentTypeError,
    build_object_key,
)
from app.models.pending_upload import MediaPurpose


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "HeadObject")


class TestBuildObjectKey:
    def test_key_is_scoped_under_purpose_and_user_id(self) -> None:
        user_id = uuid.uuid4()
        key = build_object_key(
            user_id=user_id, purpose=MediaPurpose.AVATAR, content_type="image/png"
        )
        assert key.startswith(f"avatar/{user_id}/")
        assert key.endswith(".png")

    def test_key_has_no_path_traversal_or_client_controlled_segments(self) -> None:
        user_id = uuid.uuid4()
        key = build_object_key(
            user_id=user_id, purpose=MediaPurpose.TWEET_IMAGE, content_type="image/jpeg"
        )
        # Only three segments: purpose / user_id / <uuid4>.ext — nothing a
        # client controls end up in the key besides the (already-validated)
        # content-type's extension.
        parts = key.split("/")
        assert len(parts) == 3
        assert ".." not in key
        uuid.UUID(parts[2].rsplit(".", 1)[0])  # the filename stem is a real UUID

    def test_keys_are_unique_across_calls(self) -> None:
        user_id = uuid.uuid4()
        keys = {
            build_object_key(user_id=user_id, purpose=MediaPurpose.AVATAR, content_type="image/png")
            for _ in range(50)
        }
        assert len(keys) == 50

    def test_rejects_unsupported_content_type(self) -> None:
        with pytest.raises(UnsupportedContentTypeError):
            build_object_key(
                user_id=uuid.uuid4(), purpose=MediaPurpose.AVATAR, content_type="image/gif"
            )


class TestObjectStoragePresignPut:
    async def test_delegates_to_generate_presigned_url_with_expiry(self) -> None:
        client = AsyncMock()
        client.generate_presigned_url = AsyncMock(return_value="https://minio.test/signed")
        storage = ObjectStorage(client, bucket="test-bucket")

        url = await storage.presign_put(
            key="avatar/u/x.png", content_type="image/png", expires_seconds=120
        )

        assert url == "https://minio.test/signed"
        client.generate_presigned_url.assert_awaited_once_with(
            "put_object",
            Params={"Bucket": "test-bucket", "Key": "avatar/u/x.png", "ContentType": "image/png"},
            ExpiresIn=120,
        )

    async def test_wraps_signing_failure_as_storage_error(self) -> None:
        client = AsyncMock()
        client.generate_presigned_url = AsyncMock(side_effect=_client_error("InternalError"))
        storage = ObjectStorage(client, bucket="test-bucket")

        with pytest.raises(StorageError):
            await storage.presign_put(key="k", content_type="image/png", expires_seconds=60)


class TestObjectStorageHeadObject:
    async def test_returns_metadata_when_object_exists(self) -> None:
        client = AsyncMock()
        client.head_object = AsyncMock(
            return_value={"ContentType": "image/png", "ContentLength": 1024}
        )
        storage = ObjectStorage(client, bucket="test-bucket")

        metadata = await storage.head_object("k")

        assert metadata is not None
        assert metadata.content_type == "image/png"
        assert metadata.content_length == 1024

    async def test_returns_none_when_object_missing(self) -> None:
        client = AsyncMock()
        client.head_object = AsyncMock(side_effect=_client_error("404"))
        storage = ObjectStorage(client, bucket="test-bucket")

        assert await storage.head_object("missing-key") is None

    async def test_raises_storage_error_for_unexpected_failure(self) -> None:
        client = AsyncMock()
        client.head_object = AsyncMock(side_effect=_client_error("AccessDenied"))
        storage = ObjectStorage(client, bucket="test-bucket")

        with pytest.raises(StorageError):
            await storage.head_object("k")

    async def test_raises_storage_error_when_minio_is_unreachable(self) -> None:
        client = AsyncMock()
        client.head_object = AsyncMock(side_effect=ConnectionError("connection refused"))
        storage = ObjectStorage(client, bucket="test-bucket")

        with pytest.raises(ConnectionError):
            # A non-`ClientError` transport failure (MinIO down) is not
            # swallowed/mistaken for "object missing" — it propagates so
            # callers can distinguish "confirmed absent" from "couldn't check".
            await storage.head_object("k")


class TestObjectStorageDeleteObject:
    async def test_deletes_object(self) -> None:
        client = AsyncMock()
        client.delete_object = AsyncMock(return_value={})
        storage = ObjectStorage(client, bucket="test-bucket")

        await storage.delete_object("k")

        client.delete_object.assert_awaited_once_with(Bucket="test-bucket", Key="k")

    async def test_wraps_failure_as_storage_error(self) -> None:
        client = AsyncMock()
        client.delete_object = AsyncMock(side_effect=_client_error("InternalError"))
        storage = ObjectStorage(client, bucket="test-bucket")

        with pytest.raises(StorageError):
            await storage.delete_object("k")
