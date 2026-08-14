"""Fixtures for `tests/core/`: reuses the real-Postgres `db_session` fixture
(and the one-time migration) from `tests/repositories/conftest.py` rather
than duplicating it -- `test_outbox.py` needs a real `AsyncSession`.
"""

from __future__ import annotations

from tests.repositories.conftest import _migrated_schema, db_session  # noqa: F401
