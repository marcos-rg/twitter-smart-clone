"""Post-commit callback queue: services register side effects (e.g. a Redis
`PUBLISH`) that must only run after the session's current transaction has
actually committed to PostgreSQL — never speculatively, and never at all if
the transaction rolls back.

Why this exists: `get_db_session` (`app.core.deps`) commits automatically at
the end of every request, in dependency teardown, *after* the endpoint
function/service call has already returned. A side effect fired eagerly from
inside a service method — e.g. calling `redis.publish(...)` right after
`session.add(notification)` — would run before that commit, so a crash
between the publish and the eventual commit would deliver an event for a row
that was never actually persisted (or, on rollback, never exists at all).
Queuing the side effect here and draining the queue only after
`session.commit()` succeeds closes that gap.

First consumer: the notification Redis publisher (`TSC-NOTIF-001`,
`app.services.notification_publisher`). Written generically because any
future "persist, then notify a downstream system" flow needs the identical
guarantee.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

_OUTBOX_KEY = "post_commit_callbacks"

#: A zero-argument async callable queued to run after commit. Callbacks are
#: expected to handle their own failures (log and swallow) rather than
#: raise — see `run_post_commit_callbacks`.
PostCommitCallback = Callable[[], Awaitable[None]]


def queue_post_commit(session: AsyncSession, callback: PostCommitCallback) -> None:
    """Register `callback` to run once, only after `session`'s current
    transaction commits. Never runs at all if the transaction rolls back
    instead — the caller does not need to check for that itself.
    """
    session.info.setdefault(_OUTBOX_KEY, []).append(callback)


async def run_post_commit_callbacks(session: AsyncSession) -> None:
    """Run and clear every callback queued by `queue_post_commit`.

    Call this immediately after `await session.commit()` succeeds — never
    before, and never after a rollback. Each callback is expected to catch
    and log its own failures rather than raise: this runs during request
    dependency teardown, after the response body has effectively been
    decided, so an exception escaping here would surface to the client as a
    500 for a request that actually already succeeded.
    """
    callbacks: list[PostCommitCallback] = session.info.pop(_OUTBOX_KEY, [])
    for callback in callbacks:
        await callback()
