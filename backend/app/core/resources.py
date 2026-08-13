"""Async resource lifecycle: PostgreSQL engine, Redis client, and the MinIO/S3
client, plus the readiness checks that exercise each one.

`lifespan` is registered on the FastAPI app so every resource is created once
at startup and cleanly released at shutdown (spec: "Startup and shutdown
cleanly acquire/release async resources"). Resources are stored on
`app.state` so routers/services in later tasks can depend on them without
re-creating connections per request.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import aioboto3
import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

# aioboto3's async S3 client has no first-party type stubs; typed as `Any`
# rather than pulling in the separate `types-aiobotocore` stub package.
S3Client = Any

logger = structlog.get_logger("app.resources")


@dataclass
class AppResources:
    """Handles to every async resource the app depends on."""

    db_engine: AsyncEngine
    db_sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    s3_session: aioboto3.Session
    s3_client: S3Client
    minio_bucket: str
    _s3_client_cm: Any

    async def aclose(self) -> None:
        """Release every resource. Safe to call once, at shutdown."""
        await self.db_engine.dispose()
        await self.redis.aclose()
        await self._s3_client_cm.__aexit__(None, None, None)


async def build_resources(settings: Settings) -> AppResources:
    """Create every async resource. Connections are lazy: this does not block
    on the dependencies actually being reachable, so the app can still start
    (and report liveness) even if a dependency is temporarily down; `/readyz`
    is what surfaces that.
    """
    db_engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
    )
    db_sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)

    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    s3_session = aioboto3.Session()
    s3_client_cm = s3_session.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name=settings.minio_region,
    )
    s3_client = await s3_client_cm.__aenter__()

    return AppResources(
        db_engine=db_engine,
        db_sessionmaker=db_sessionmaker,
        redis=redis,
        s3_session=s3_session,
        s3_client=s3_client,
        minio_bucket=settings.minio_bucket,
        _s3_client_cm=s3_client_cm,
    )


async def check_database(resources: AppResources, timeout: float) -> bool:
    """Readiness check: can we round-trip a trivial query against PostgreSQL?"""
    try:
        async with asyncio.timeout(timeout), resources.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        await logger.awarning("readiness_check_failed", dependency="postgres", exc_info=True)
        return False


async def check_redis(resources: AppResources, timeout: float) -> bool:
    """Readiness check: does Redis answer `PING`?"""
    try:
        async with asyncio.timeout(timeout):
            return bool(await resources.redis.ping())
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        await logger.awarning("readiness_check_failed", dependency="redis", exc_info=True)
        return False


async def check_object_storage(resources: AppResources, timeout: float) -> bool:
    """Readiness check: is the configured MinIO/S3 bucket reachable?"""
    try:
        async with asyncio.timeout(timeout):
            await resources.s3_client.head_bucket(Bucket=resources.minio_bucket)
        return True
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        await logger.awarning("readiness_check_failed", dependency="minio", exc_info=True)
        return False


def create_lifespan(settings: Settings) -> Any:
    """Build the FastAPI `lifespan` context manager bound to `settings`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = await build_resources(settings)
        app.state.resources = resources
        app.state.settings = settings
        try:
            yield
        finally:
            await resources.aclose()

    return lifespan
