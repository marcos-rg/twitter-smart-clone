"""Structured JSON logging configuration (`structlog`).

Every log line is a single JSON object on stdout. The access-log middleware
(`app.core.middleware.RequestContextMiddleware`) binds `request_id`, `method`,
`path`, `status_code`, and `duration_ms` via `structlog.contextvars` so they
appear on every log emitted while handling a request, without threading a
logger through every function call.

Secrets (passwords, tokens, Authorization headers, cookies) must never be
logged; call sites are responsible for not passing them as event fields, and
`_redact_sensitive_keys` provides a defense-in-depth filter for the most
common accidental leaks.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_SENSITIVE_KEYS = {
    "password",
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "cookie",
    "set-cookie",
    "jwt_secret_key",
    "secret",
}


def _redact_sensitive_keys(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Redact well-known sensitive field names before a log event is rendered."""
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure stdlib logging + structlog to emit structured JSON to stdout."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_sensitive_keys,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(*args: Any, **kwargs: Any) -> Any:
    """Return a structlog logger bound with the given initial context."""
    return structlog.get_logger(*args, **kwargs)
