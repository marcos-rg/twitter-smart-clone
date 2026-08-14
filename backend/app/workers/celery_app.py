"""Celery application wiring (spec §12.1/§8): Redis-backed broker + result
backend shared with the API. Task modules for specific features (AI
generation, notification fan-out) are added by later tasks; this module only
establishes the configured `Celery` instance the `worker`/`beat` containers
and future `@celery_app.task` definitions point at.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "twitter_smart_clone",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
    # Task modules register themselves onto this `Celery` instance via
    # `@celery_app.task` when imported; `include` is what makes the
    # `worker` process actually import them (it only imports this module
    # via `-A app.workers.celery_app`, not the rest of `app.workers`).
    include=["app.workers.media_cleanup"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Intended cadence for `app.workers.media_cleanup.cleanup_abandoned_uploads`
    # (TSC-MEDIA-001). Inert until a `beat` service is added alongside
    # `worker` in `docker-compose.yml` (`docker-compose.yml`'s `worker`
    # comment: "`beat` (periodic tasks) is deferred") — until then this task
    # runs on manual/cron invocation (see that module's docstring).
    beat_schedule={
        "cleanup-abandoned-media-uploads": {
            "task": "app.workers.media_cleanup.cleanup_abandoned_uploads",
            "schedule": 3600.0,  # hourly
        },
    },
)
