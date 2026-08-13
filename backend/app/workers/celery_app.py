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
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
