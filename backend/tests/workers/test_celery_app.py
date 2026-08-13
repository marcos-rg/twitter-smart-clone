"""Tests for the shared Celery app wiring (`app.workers.celery_app`)."""

from __future__ import annotations

from app.workers.celery_app import celery_app


def test_celery_app_uses_redis_broker_and_backend() -> None:
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.result_backend.startswith("redis://")


def test_celery_app_uses_json_serialization() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_celery_app_tracks_started_tasks() -> None:
    assert celery_app.conf.task_track_started is True
