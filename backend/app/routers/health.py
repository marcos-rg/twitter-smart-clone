"""Liveness/readiness endpoints (spec §10.4): `/healthz` for liveness (no
dependency checks — must respond even if PostgreSQL/Redis/MinIO are down) and
`/readyz` for readiness (fails with 503 if any required dependency is
unreachable).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.resources import AppResources, check_database, check_object_storage, check_redis

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Return 200 as long as the process is up. Never checks dependencies."""
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readyz(request: Request) -> JSONResponse:
    """Return 200 only when every required dependency is reachable, else 503."""
    resources: AppResources = request.app.state.resources
    timeout = request.app.state.settings.readiness_check_timeout_seconds

    database_ready, redis_ready, storage_ready = await asyncio.gather(
        check_database(resources, timeout),
        check_redis(resources, timeout),
        check_object_storage(resources, timeout),
    )
    checks = {
        "database": "ok" if database_ready else "unavailable",
        "redis": "ok" if redis_ready else "unavailable",
        "object_storage": "ok" if storage_ready else "unavailable",
    }
    all_ready = database_ready and redis_ready and storage_ready

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ready else "not_ready", "checks": checks},
    )
