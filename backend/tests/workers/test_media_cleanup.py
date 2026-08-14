"""Integration tests for `app.workers.media_cleanup` (TSC-MEDIA-001) against
real PostgreSQL and real MinIO, plus a mocked-storage-failure path.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic import command
from app.core.config import Settings
from app.core.resources import build_resources
from app.core.storage import ObjectStorage, StorageError, build_storage
from app.models.base import utcnow
from app.models.pending_upload import MediaPurpose, PendingUpload, PendingUploadStatus
from app.models.user import User
from app.repositories.pending_uploads import PendingUploadRepository
from app.workers.media_cleanup import _cleanup_abandoned_uploads, cleanup_abandoned_uploads
from tests.repositories.conftest import _alembic_config

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://twitter_smart_clone:twitter_smart_clone_dev"
        "@localhost:5432/twitter_smart_clone",
    ),
)


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema_for_media_cleanup() -> None:
    command.upgrade(_alembic_config(), "head")


@pytest.fixture
def cleanup_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        media_abandoned_upload_ttl_hours=24,
    )


@pytest_asyncio.fixture
async def db_session(cleanup_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(cleanup_settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE notifications, refresh_tokens, likes, follows, "
                "tweet_media, tweets, pending_uploads, users CASCADE"
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


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


def _pending_row(
    *,
    user_id: UUID,
    key: str,
    created_at: datetime,
    status: PendingUploadStatus = PendingUploadStatus.PENDING,
) -> PendingUpload:
    return PendingUpload(
        user_id=user_id,
        purpose=MediaPurpose.AVATAR,
        s3_key=key,
        content_type="image/png",
        size_bytes=1024,
        status=status,
        presign_expires_at=created_at,
        created_at=created_at,
    )


async def test_cleanup_reaps_old_pending_rows_and_their_objects(
    cleanup_settings: Settings, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session, "cleanup_owner")
    long_ago = utcnow() - timedelta(hours=48)
    recently = utcnow() - timedelta(minutes=5)

    abandoned_with_object = _pending_row(
        user_id=user.id, key=f"avatar/{user.id}/old-uploaded.png", created_at=long_ago
    )
    abandoned_without_object = _pending_row(
        user_id=user.id, key=f"avatar/{user.id}/old-never-uploaded.png", created_at=long_ago
    )
    still_fresh = _pending_row(
        user_id=user.id, key=f"avatar/{user.id}/fresh.png", created_at=recently
    )
    old_but_confirmed = _pending_row(
        user_id=user.id,
        key=f"avatar/{user.id}/old-confirmed.png",
        created_at=long_ago,
        status=PendingUploadStatus.CONFIRMED,
    )
    for row in (abandoned_with_object, abandoned_without_object, still_fresh, old_but_confirmed):
        db_session.add(row)
    await db_session.commit()

    # Actually put an object in MinIO for the first abandoned row, so the
    # cleanup's delete is verifiable against real storage, not just the DB.
    resources = await build_resources(cleanup_settings)
    storage = build_storage(resources)
    try:
        await resources.s3_client.put_object(
            Bucket=resources.minio_bucket,
            Key=abandoned_with_object.s3_key,
            Body=b"leftover-bytes",
            ContentType="image/png",
        )
        assert await storage.head_object(abandoned_with_object.s3_key) is not None

        reaped = await _cleanup_abandoned_uploads(cleanup_settings)
        assert reaped == 2

        # The object was actually deleted from MinIO.
        assert await storage.head_object(abandoned_with_object.s3_key) is None
    finally:
        await resources.aclose()

    # Only the two abandoned rows are gone; fresh and confirmed rows survive.
    engine = create_async_engine(cleanup_settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as fresh_session:
        repo = PendingUploadRepository(fresh_session)
        assert await repo.get_by_key(abandoned_with_object.s3_key) is None
        assert await repo.get_by_key(abandoned_without_object.s3_key) is None
        assert await repo.get_by_key(still_fresh.s3_key) is not None
        assert await repo.get_by_key(old_but_confirmed.s3_key) is not None
    await engine.dispose()


async def test_cleanup_still_deletes_row_when_storage_delete_fails(
    cleanup_settings: Settings, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A storage outage while deleting the (possibly nonexistent) object
    must not block reaping the stale row — otherwise a permanently-broken
    key would wedge the sweep forever.
    """
    user = await _make_user(db_session, "cleanup_owner_2")
    long_ago = utcnow() - timedelta(hours=48)
    row = _pending_row(user_id=user.id, key=f"avatar/{user.id}/broken.png", created_at=long_ago)
    db_session.add(row)
    await db_session.commit()

    async def _boom(self: ObjectStorage, key: str) -> None:
        raise StorageError("simulated MinIO outage")

    monkeypatch.setattr(ObjectStorage, "delete_object", _boom)

    reaped = await _cleanup_abandoned_uploads(cleanup_settings)
    assert reaped == 1

    engine = create_async_engine(cleanup_settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as fresh_session:
        repo = PendingUploadRepository(fresh_session)
        assert await repo.get_by_key(row.s3_key) is None
    await engine.dispose()


async def test_cleanup_is_a_no_op_when_nothing_is_abandoned(
    cleanup_settings: Settings, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session, "cleanup_owner_3")
    db_session.add(
        _pending_row(user_id=user.id, key=f"avatar/{user.id}/fresh.png", created_at=utcnow())
    )
    await db_session.commit()

    assert await _cleanup_abandoned_uploads(cleanup_settings) == 0


def test_celery_task_entry_point_runs_synchronously(db_session: AsyncSession) -> None:
    """The registered Celery task (`cleanup_abandoned_uploads`, the sync
    `asyncio.run(...)` wrapper around `_cleanup_abandoned_uploads`) is what
    `celery ... call app.workers.media_cleanup.cleanup_abandoned_uploads`
    (or, once wired, a `beat` schedule) actually invokes — exercised here
    via Celery's `.run()` against the same (default-settings) database/MinIO
    the `backend`/`worker` containers share.
    """
    reaped = cleanup_abandoned_uploads.run()
    assert isinstance(reaped, int)
    assert reaped >= 0
