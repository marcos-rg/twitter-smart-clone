# Notification persistence and delivery APIs (TSC-NOTIF-001)

Backend resource for notification listing, mark-read, and post-commit Redis
publication. Trigger wiring — actually *calling* `NotificationsService.create_notification`
when a follow/like/reply happens — is out of scope here and belongs to the
tasks that own those actions (`TSC-SOC-*`, `TSC-LIKE-*`, `TSC-TWEET-*`). Live
WebSocket delivery of the published events is
[`TSC-NOTIF-004`](./websocket-realtime.md).

## API surface

- `GET /api/v1/notifications` — the caller's notifications, newest first,
  cursor-paginated (`data` + `page.next_cursor`), plus a top-level
  `unread_count` independent of the current page. Each item embeds an
  `actor` summary (`id`, `username`, `name`, `avatar_key`) resolved via a
  single batched query, not N+1.
- `POST /api/v1/notifications/read` — mark notifications read.
  - Body `{}` or `{"notification_ids": null}` marks **all** currently-unread
    notifications.
  - Body `{"notification_ids": [...]}` marks only those ids. Ids that don't
    exist, or belong to another user, are **silently excluded** rather than
    erroring — a 404/403 here would let a client probe whether some other
    user's notification id exists.
  - Response: `{"marked_read": <int>, "unread_count": <int>}`. Both mark
    operations are idempotent: calling again with the same target(s) returns
    `marked_read: 0` and the unread state is never double-flipped, because
    the underlying `UPDATE` only ever matches currently-unread rows.
- Both endpoints require authentication and are scoped to the caller by
  construction (`recipient_id = current_user.id` in every query) — there is
  no code path that can return or mutate another user's notifications.

## Notification creation and the event envelope (human-review focus)

`NotificationsService.create_notification(*, recipient_id, actor, type_, tweet_id)`
is the only way a notification row is created. It:

1. No-ops (returns `None`) when `recipient_id == actor.id` — a user is never
   notified of their own action. This guard lives here so trigger-wiring
   tasks don't each need to reimplement it.
2. Persists the row (`INSERT`, flushed not committed).
3. Builds the event envelope and queues its publish via
   `app.core.outbox.queue_post_commit` — it does **not** publish immediately.

The envelope (`app.schemas.notifications.NotificationEvent`), `PUBLISH`ed as
JSON to Redis channel `notifications:{recipient_id}` (spec §4.2):

```json
{
  "type": "notification",
  "event": "follow | like | reply",
  "data": {
    "notification_id": "...",
    "recipient_id": "...",
    "actor": { "id": "...", "username": "...", "name": "...", "avatar_key": "..." },
    "tweet_id": "...",
    "is_read": false,
    "created_at": "..."
  }
}
```

`notification_id` is the row's primary key — identical to the `id` returned
by `GET /notifications` — so clients de-duplicate a live push against a
REST-fetched item by that single field (spec §4.2). Two fields go beyond the
spec's abbreviated example and are the specific additions the human review
gate should confirm:

- **`recipient_id`** — lets a WebSocket handler verify/route the event
  without trusting the Redis channel name alone.
- **`is_read`** — always `false` at publish time, included so this payload
  is a strict superset of the REST `NotificationItem` shape and needs no
  special-casing on the client.

## Post-commit publishing (`app.core.outbox`)

`get_db_session` (`app.core.deps`) commits automatically at the end of every
request, in dependency teardown — *after* the endpoint/service call has
already returned. Publishing eagerly from inside a service method would run
before that commit, so a crash between the publish and the eventual commit
could deliver an event for a row that was never actually persisted.

`app.core.outbox` closes that gap generically:

- `queue_post_commit(session, callback)` — register a zero-arg async
  callback on the session; queuing it never runs it.
- `run_post_commit_callbacks(session)` — run and clear every queued
  callback. `get_db_session` calls this immediately after every branch that
  commits (the normal success path *and* the handled-`AppError` path, which
  also commits deliberately). The rollback branch (unexpected exception)
  never calls it, so a queued callback for a transaction that never
  committed simply never runs.
- Callbacks must swallow their own failures rather than raise — this runs
  during dependency teardown, after the response has effectively been
  decided, so an exception escaping here would surface to the client as a
  `500` for a request that already succeeded.

`app.services.notification_publisher.publish_notification_event` is the
first (and, at this task, only) consumer: a Redis publish failure is logged
and swallowed, never raised — the notification row is already durably
committed by the time this runs, so the recipient still sees it on their
next `GET /notifications` fetch even if the live push is lost (spec §4.2:
"WebSocket is a delivery accelerator, not the source of truth — the DB is").

## Layout

```
backend/app/
├── core/
│   └── outbox.py                    # generic post-commit callback queue
├── models/notification.py           # Notification, NotificationType (TSC-DATA-001)
├── repositories/notifications.py    # list_for_recipient, count_unread,
│                                     #   mark_all_read, mark_selected_read
├── schemas/notifications.py         # REST schemas + NotificationEvent envelope
├── services/
│   ├── notifications.py             # NotificationsService (create/list/mark-read)
│   └── notification_publisher.py    # Redis PUBLISH to notifications:{recipient_id}
└── routers/notifications.py         # GET /notifications, POST /notifications/read
```

## Verification commands

- `uv run pytest tests/core/test_outbox.py tests/core/test_deps_post_commit.py`
  — the generic commit-before-publish / rollback-publishes-nothing guarantee,
  exercised against toy routes (no notification code involved) so it's
  verified at the platform layer that actually provides it.
- `uv run pytest tests/services/test_notifications_service.py` — the exact
  event envelope shape, commit-before-publish and rollback-publishes-nothing
  against the real notification publisher, the self-notification no-op, and
  actor resolution in `list_for_recipient`, all against a real Postgres
  session and a real Redis pub/sub subscription.
- `uv run pytest tests/repositories/test_repositories.py` — `mark_all_read`/
  `mark_selected_read` idempotency and cross-recipient scoping at the
  repository layer.
- `uv run pytest tests/test_notifications.py` — the full HTTP contract:
  auth-required, recipient-only visibility with accurate `unread_count`,
  cursor-stable pagination with a malformed-cursor `400`, and mark-all/
  mark-selected idempotency over real HTTP requests.

All of the above, plus the full existing suite (144 tests total), pass with
98% statement coverage (gate: 90%) via
`docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"`.
`uv run ruff check .`, `uv run ruff format --check .`, and
`uv run mypy app tests scripts` all pass against every file this task added
or modified (pre-existing formatting drift in `app/repositories/tweet_media.py`,
unrelated to this task, is untouched).
