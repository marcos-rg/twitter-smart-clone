"""Tests for structured JSON logging (spec §10.4): request id, method, path,
status, latency, and secret redaction.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.logging import _redact_sensitive_keys, configure_logging, get_logger


def test_access_log_line_has_the_documented_shape(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A completed request emits one JSON log line with the required fields."""
    capsys.readouterr()  # discard startup noise

    client.get("/healthz", headers={"X-Request-ID": "log-shape-test"})

    captured = capsys.readouterr()
    log_lines = [
        json.loads(line)
        for line in captured.out.splitlines()
        if line.strip().startswith("{") and "request_completed" in line
    ]
    assert log_lines, f"no access log line found in output: {captured.out!r}"
    record = log_lines[-1]

    assert record["request_id"] == "log-shape-test"
    assert record["method"] == "GET"
    assert record["path"] == "/healthz"
    assert record["status_code"] == 200
    assert isinstance(record["duration_ms"], (int, float))


def test_access_log_line_has_no_secrets(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Request headers like `Authorization`/cookies must never reach the logs."""
    capsys.readouterr()

    client.get(
        "/healthz",
        headers={"Authorization": "Bearer super-secret-token", "Cookie": "refresh=abc123"},
    )

    captured = capsys.readouterr()
    assert "super-secret-token" not in captured.out
    assert "abc123" not in captured.out


def test_redact_sensitive_keys_masks_known_secret_fields() -> None:
    event = {
        "password": "hunter2",
        "authorization": "Bearer xyz",
        "token": "abc",
        "safe_field": "keep-me",
    }

    redacted = _redact_sensitive_keys(None, "info", dict(event))

    assert redacted["password"] == "***redacted***"
    assert redacted["authorization"] == "***redacted***"
    assert redacted["token"] == "***redacted***"
    assert redacted["safe_field"] == "keep-me"


def test_get_logger_returns_a_usable_bound_logger(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    capsys.readouterr()

    logger = get_logger("test.module")
    logger.info("standalone_event", foo="bar")

    captured = capsys.readouterr()
    assert "standalone_event" in captured.out
    assert "foo" in captured.out
