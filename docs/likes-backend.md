# Likes backend (TSC-LIKE-001)

Backend slice for like/unlike, the transactional `tweets.like_count` counter
+ new-like notification side effect, and the periodic counter-reconciliation
safety net.

## API surface

- `POST /api/v1/tweets/{tweet_id}/like` — like (idempotent).
- `DELETE /api/v1/tweets/{tweet_id}/like` — unlike (idempotent).
  Both return `{"liked": bool, "like_count": int}` — the tweet's updated
  state, so the client can render from this response alone (mirrors
  `FollowRelationship`'s shape from `TSC-SOC-001`). `404 not_found` if the
  tweet doesn't exist; `401 unauthenticated` without a valid access token.
- Every tweet-reading endpoint (`GET /tweets/{id}`, `/tweets/{id}/replies`,
  `/users/{username}/tweets`, `/feed`) already carries `like_count` and
  `liked_by_viewer` on `TweetView` (`TSC-TWEET-001`'s `LikeRepository`
  scaffold) — this task is what actually makes those fields move.

## Idempotency contract (human-review focus)

Mirrors `app.services.follows`'s follow/unfollow contract (`TSC-SOC-001`),
adapted for likes:

- **Like is idempotent**: a repeat like call — including a genuine
  concurrent race — leaves exactly one `likes` row, exactly one
  `like_count` increment, and creates *no* second notification.
  `LikeRepository.like()` uses `INSERT ... ON CONFLICT DO NOTHING` on the
  `(user_id, tweet_id)` primary key (no separate exists-check/SAVEPOINT
  needed, unlike follows — the composite PK is the whole idempotency
  mechanism), and `LikesService.like()` only bumps the counter and notifies
  when `like()` reports a freshly-inserted row.
- **Unlike is idempotent**: unliking a tweet you haven't liked is a no-op,
  not an error, and never creates or removes a notification (unlike never
  notifies at all, and the original like notification is never retracted).
- **Self-like never notifies**: liking your own tweet inserts the `likes`
  row and bumps `like_count` like any other like, but creates no
  notification. This is enforced by `NotificationsService.create_notification`'s
  existing `recipient_id == actor.id` no-op guard (`TSC-NOTIF-001`) — the
  same backstop `follows`/`tweets` (replies) rely on — not a separate check
  in `LikesService`. **This is the approved decision this task's human
  review gate covers.**
- **Counter update is atomic and commits in the same transaction as the
  like/unlike row and the notification.** `LikesService.like()`/`.unlike()`
  never call `session.commit()` (only `flush()`), so
  `app.core.deps.get_db_session` commits the like/unlike row, the
  `tweets.like_count` update, and the notification insert together, or none
  of them land.

## Atomic, non-negative counter update

`TweetRepository.increment_like_count` was scaffolded by `TSC-TWEET-001` as
a read-modify-write through the ORM (`tweet.like_count += delta`) — safe for
`reply_count` only because the same pattern there (`increment_reply_count`)
was already a relative SQL update. This task fixes `increment_like_count` to
match: a relative

```sql
UPDATE tweets SET like_count = GREATEST(0, like_count + delta) WHERE id = :id
```

so two concurrent like/unlike calls for the same tweet each issue their own
atomic increment — PostgreSQL serializes the two `UPDATE`s via the row lock,
and both land correctly (no lost update, unlike a read-then-write pattern
would produce under a race). `GREATEST(0, ...)` is a defensive floor: the
like/unlike idempotency contract above should already keep `like_count`
from going negative, but this makes "counters never go negative" true at
the database level too.

Because that `UPDATE` runs at the SQLAlchemy Core level, it bypasses this
request's ORM identity map — the already-loaded `Tweet` Python object
wouldn't see the new value without an explicit refresh. `LikesService`
sidesteps this entirely by computing the `like_count` it returns from
`LikeRepository.count_for_tweet` (`SELECT COUNT(*) FROM likes WHERE
tweet_id = ...`) rather than re-reading the just-updated ORM object, so the
response is always correct regardless of identity-map staleness.

## Rate limiting

- Both `POST` and `DELETE /tweets/{id}/like` share one per-user
  sliding-window limit, keyed `like:{user_id}`, default
  `like_rate_limit_per_minute = 60` (spec §10.3: "likes/follows
  60/min/user") — a separate config key and Redis key prefix from
  `follow_rate_limit_per_minute`/`follow:{user_id}` so the two resources'
  windows never share state. Exceeding it returns `429 rate_limited` with a
  `Retry-After` header.

## Counter reconciliation (periodic safety net)

`app.workers.reconcile_counters.reconcile_counters` is a Celery task
(spec §5.3: "a periodic Celery task can reconcile counters as a safety
net") that recomputes both `tweets.like_count` (from `likes`) and
`tweets.reply_count` (from `tweets` grouped by `parent_tweet_id`) via two
set-based `UPDATE ... FROM` statements and repairs only the rows that have
actually drifted, returning how many of each it fixed. It covers both
counters — not just likes — because `app.models.tweet`'s docstring defers
reconciliation for *both* denormalized counters to "a later task" as one
unit, and no other task in `specification/tasks.md` ever revisits
`reply_count` reconciliation.

Registered in `celery_app.conf.beat_schedule` at a 15-minute cadence,
alongside `TSC-MEDIA-001`'s hourly `cleanup-abandoned-media-uploads` entry —
inert until a `beat` service is added to `docker-compose.yml` (still
deferred per `TSC-CORE-001`), so until then it runs on manual/cron
invocation: `celery -A app.workers.celery_app call
app.workers.reconcile_counters.reconcile_counters`.

Under normal operation this task finds nothing to repair, since
`LikesService`/`TweetsService` already keep both counters correct
transactionally — it exists to catch drift from anything that bypasses
that code path (a manual DB fix, an untested edge case, direct seed-data
inserts), not a path this codebase takes regularly.

## Verification commands

- `uv run pytest tests/test_likes.py` — full HTTP contract: idempotent
  like/unlike, 401/404 paths, the like → notification delivery path,
  self-like creating no notification, rate limiting (429 + `Retry-After`),
  a concurrent-duplicate-like-requests race settling to exactly one row/one
  notification, and a mixed concurrent like/unlike race settling to a
  non-negative, consistent (0 or 1) `like_count`.
- `uv run pytest tests/services/test_likes_service.py` — service-layer
  transactionality: exactly one notification after commit, idempotent
  repeat like/unlike, self-like notifying no one, not-found errors, and a
  multi-session concurrency race (5 concurrent `like()` calls on separate
  connections/sessions settle to exactly one `likes` row, `like_count == 1`,
  and one notification).
- `uv run pytest tests/workers/test_reconcile_counters.py` — deliberately
  drifts `like_count` both upward and downward (nonexistent likes counted,
  real likes uncounted) and `reply_count` downward, confirms the task
  repairs exactly the drifted rows, leaves already-correct rows untouched,
  and is a no-op on a second run; plus the sync Celery entry-point smoke
  test.
- Full backend suite: `uv run pytest -q` — 308 tests pass; `ruff check .`
  and `mypy app` are both clean.
