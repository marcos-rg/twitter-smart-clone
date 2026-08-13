"""Tests for `RequestContextMiddleware` request-id behavior not already
covered by `tests/test_errors.py::test_request_id_from_client_is_echoed_back`.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_request_id_is_generated_when_not_supplied(client: TestClient) -> None:
    response = client.get("/healthz")

    request_id = response.headers["x-request-id"]
    # A valid UUID4 string proves one was generated, not just echoed/blank.
    assert uuid.UUID(request_id).version == 4


def test_each_request_gets_a_distinct_generated_request_id(client: TestClient) -> None:
    first = client.get("/healthz").headers["x-request-id"]
    second = client.get("/healthz").headers["x-request-id"]

    assert first != second
