"""Unit/integration tests for `MediaService` (TSC-MEDIA-001, spec §8.4).

Runs against a real PostgreSQL session (`pending_uploads`/`users` rows must
really persist and be queryable) but a fake, in-memory `ObjectStorage`
double (`FakeStorage`) rather than real MinIO — this is the "mocked storage
failures" half of the task's verification requirement; `tests/test_media.py`
covers the real-MinIO integration half.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.storage import ObjectMetadata, StorageError
from app.models.pending_upload import MediaPurpose
from app.models.user import User
from app.repositories.pending_uploads import PendingUploadRepository
from app.schemas.media import PresignFileRequest
from app.services.media import (
    MediaAlreadyConfirmedError,
    MediaForbiddenError,
    MediaLimits,
    MediaMetadataMismatchError,
    MediaNotFoundError,
    MediaObjectMissingError,
    MediaPurposeMismatchError,
    MediaService,
    MediaTooLargeError,
    TooManyMediaFilesError,
    UnsupportedMediaTypeError,
)
from tests.repositories.conftest import TEST_DATABASE_URL


class FakeStorage:
    """In-memory `SupportsObjectStorage` double. `objects` simulates what
    actually landed in the bucket: a test "uploads" to a key by adding it
    here, independent of what was declared at presign time, so tests can
    assert on real vs. declared metadata mismatches.
    """

    def __init__(self) -> None:
        self.objects: dict[str, ObjectMetadata] = {}
        self.presigned: list[str] = []
        self.deleted: list[str] = []
        self.fail_head_object = False

    async def presign_put(self, *, key: str, content_type: str, expires_seconds: int) -> str:
        self.presigned.append(key)
        return f"http://minio.test/{key}?signature=fake&expires={expires_seconds}"

    async def head_object(self, key: str) -> ObjectMetadata | None:
        if self.fail_head_object:
            raise StorageError("simulated storage outage")
        return self.objects.get(key)

    async def delete_object(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    def put(self, key: str, *, content_type: str, size: int) -> None:
        """Simulate a client uploading a real object to `key`."""
        self.objects[key] = ObjectMetadata(content_type=content_type, content_length=size)


async def _make_user(session: AsyncSession, username: str) -> User:
    user = User(
        name=username.title(),
        username=username,
        email=f"{username}@example.com",
        password_hash="hash",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def limits() -> MediaLimits:
    return MediaLimits(
        max_image_bytes=5 * 1024 * 1024, max_tweet_images=4, presign_expires_seconds=300
    )


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest_asyncio.fixture
async def service(
    db_session: AsyncSession, storage: FakeStorage, limits: MediaLimits
) -> MediaService:
    return MediaService(PendingUploadRepository(db_session), storage, limits)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "media_owner")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "media_other")


# --- presign -----------------------------------------------------------------


@pytest.mark.parametrize(
    "content_type", ["image/png", "image/jpeg", "image/webp"], ids=["png", "jpeg", "webp"]
)
async def test_presign_accepts_every_allowed_content_type(
    service: MediaService, storage: FakeStorage, user: User, content_type: str
) -> None:
    uploads = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type=content_type, size_bytes=1024)],
    )
    assert len(uploads) == 1
    assert uploads[0].key in storage.presigned
    # Object key is randomized and user-scoped, not derived from client input.
    assert uploads[0].key.startswith(f"avatar/{user.id}/")
    assert uploads[0].key.endswith(
        {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]
    )


async def test_presign_object_keys_are_unique_per_call(service: MediaService, user: User) -> None:
    first = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=1024)],
    )
    second = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=1024)],
    )
    assert first[0].key != second[0].key


async def test_presign_rejects_unsupported_content_type(service: MediaService, user: User) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        await service.presign_batch(
            user,
            purpose=MediaPurpose.TWEET_IMAGE,
            files=[PresignFileRequest(content_type="image/gif", size_bytes=1024)],
        )


async def test_presign_rejects_oversized_file(
    service: MediaService, user: User, limits: MediaLimits
) -> None:
    with pytest.raises(MediaTooLargeError):
        await service.presign_batch(
            user,
            purpose=MediaPurpose.TWEET_IMAGE,
            files=[
                PresignFileRequest(content_type="image/png", size_bytes=limits.max_image_bytes + 1)
            ],
        )


async def test_presign_rejects_more_than_four_tweet_images(
    service: MediaService, user: User
) -> None:
    files = [PresignFileRequest(content_type="image/png", size_bytes=1024) for _ in range(5)]
    with pytest.raises(TooManyMediaFilesError):
        await service.presign_batch(user, purpose=MediaPurpose.TWEET_IMAGE, files=files)


async def test_presign_allows_exactly_four_tweet_images(service: MediaService, user: User) -> None:
    files = [PresignFileRequest(content_type="image/png", size_bytes=1024) for _ in range(4)]
    uploads = await service.presign_batch(user, purpose=MediaPurpose.TWEET_IMAGE, files=files)
    assert len(uploads) == 4


async def test_presign_rejects_more_than_one_avatar_file(service: MediaService, user: User) -> None:
    files = [PresignFileRequest(content_type="image/png", size_bytes=1024) for _ in range(2)]
    with pytest.raises(TooManyMediaFilesError):
        await service.presign_batch(user, purpose=MediaPurpose.AVATAR, files=files)


async def test_presign_rejects_whole_batch_when_any_file_invalid(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    """No partial presigns: an invalid file anywhere in the batch rejects
    the entire request before any presigned URL is issued.
    """
    files = [
        PresignFileRequest(content_type="image/png", size_bytes=1024),
        PresignFileRequest(content_type="image/gif", size_bytes=1024),
    ]
    with pytest.raises(UnsupportedMediaTypeError):
        await service.presign_batch(user, purpose=MediaPurpose.TWEET_IMAGE, files=files)
    assert storage.presigned == []


# --- confirm -------------------------------------------------------------------


async def test_confirm_avatar_persists_avatar_key_on_user(
    service: MediaService, storage: FakeStorage, user: User, db_session: AsyncSession
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    storage.put(upload.key, content_type="image/png", size=2048)

    confirmed = await service.confirm_avatar(user, key=upload.key)

    assert confirmed.key == upload.key
    assert user.avatar_key == upload.key

    # Fresh read proves the value was actually persisted, not just mutated
    # on the in-memory object (spec: "remains present after a fresh profile
    # read").
    await db_session.commit()

    # Re-read through an entirely separate session/connection (not just an
    # expired identity-map entry) to prove the value was actually
    # persisted to PostgreSQL.
    engine = create_async_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as fresh_session:
        result = await fresh_session.exec(select(User).where(User.id == user.id))
        reloaded = result.one()
    await engine.dispose()
    assert reloaded.avatar_key == upload.key


async def test_confirm_rejects_object_that_was_never_uploaded(
    service: MediaService, user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    # Never calls storage.put(...): nothing actually landed in the bucket.
    with pytest.raises(MediaObjectMissingError):
        await service.confirm_avatar(user, key=upload.key)


async def test_confirm_rejects_altered_content_type(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    # Client uploaded a different content-type than it declared at presign time.
    storage.put(upload.key, content_type="image/jpeg", size=2048)

    with pytest.raises(MediaMetadataMismatchError):
        await service.confirm_avatar(user, key=upload.key)


async def test_confirm_rejects_altered_size(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    storage.put(upload.key, content_type="image/png", size=999_999)

    with pytest.raises(MediaMetadataMismatchError):
        await service.confirm_avatar(user, key=upload.key)


async def test_confirm_rejects_key_owned_by_another_user(
    service: MediaService, storage: FakeStorage, user: User, other_user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    storage.put(upload.key, content_type="image/png", size=2048)

    with pytest.raises(MediaForbiddenError):
        await service.confirm_avatar(other_user, key=upload.key)


async def test_confirm_rejects_unknown_key(service: MediaService, user: User) -> None:
    with pytest.raises(MediaNotFoundError):
        await service.confirm_avatar(user, key="avatar/does-not-exist/nope.png")


async def test_confirm_rejects_purpose_mismatch(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.TWEET_IMAGE,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    storage.put(upload.key, content_type="image/png", size=2048)

    with pytest.raises(MediaPurposeMismatchError):
        await service.confirm_avatar(user, key=upload.key)


async def test_confirm_rejects_more_than_four_tweet_image_keys(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    files = [PresignFileRequest(content_type="image/png", size_bytes=1024) for _ in range(4)]
    uploads = await service.presign_batch(user, purpose=MediaPurpose.TWEET_IMAGE, files=files)
    for upload in uploads:
        storage.put(upload.key, content_type="image/png", size=1024)
    extra_upload = (
        await service.presign_batch(
            user,
            purpose=MediaPurpose.TWEET_IMAGE,
            files=[PresignFileRequest(content_type="image/png", size_bytes=1024)],
        )
    )[0]
    storage.put(extra_upload.key, content_type="image/png", size=1024)

    keys = [u.key for u in uploads] + [extra_upload.key]
    with pytest.raises(TooManyMediaFilesError):
        await service.confirm_keys(user, purpose=MediaPurpose.TWEET_IMAGE, keys=keys)


async def test_confirm_tweet_images_returns_all_confirmed_media(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    files = [PresignFileRequest(content_type="image/png", size_bytes=1024) for _ in range(3)]
    uploads = await service.presign_batch(user, purpose=MediaPurpose.TWEET_IMAGE, files=files)
    for upload in uploads:
        storage.put(upload.key, content_type="image/png", size=1024)

    confirmed = await service.confirm_keys(
        user, purpose=MediaPurpose.TWEET_IMAGE, keys=[u.key for u in uploads]
    )
    assert {c.key for c in confirmed} == {u.key for u in uploads}


async def test_confirm_rejects_already_confirmed_key(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    storage.put(upload.key, content_type="image/png", size=2048)
    await service.confirm_avatar(user, key=upload.key)

    with pytest.raises(MediaAlreadyConfirmedError):
        await service.confirm_avatar(user, key=upload.key)


# --- storage failure path (mocked) --------------------------------------------


async def test_confirm_propagates_storage_outage_as_storage_error(
    service: MediaService, storage: FakeStorage, user: User
) -> None:
    [upload] = await service.presign_batch(
        user,
        purpose=MediaPurpose.AVATAR,
        files=[PresignFileRequest(content_type="image/png", size_bytes=2048)],
    )
    storage.fail_head_object = True

    with pytest.raises(StorageError):
        await service.confirm_avatar(user, key=upload.key)
