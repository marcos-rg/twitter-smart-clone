# Follow graph backend (TSC-SOC-001)

Backend slice for follow/unfollow, follower/following lists, profile
relationship/count fields, and the follow → notification side effect.

## API surface

- `POST /api/v1/users/{username}/follow` — follow (idempotent).
- `DELETE /api/v1/users/{username}/follow` — unfollow (idempotent).
  Both return `{"following": bool, "followers_count": int}` — the target's
  updated state, so the client can render from this response alone.
- `GET /api/v1/users/{username}/followers` — cursor-paginated followers list.
- `GET /api/v1/users/{username}/following` — cursor-paginated following list.
  Both return the `data` + `page.next_cursor` envelope, same shape as
  `GET /users/{username}/tweets` and `GET /users/search`.
- `GET /api/v1/users/{username}` (extended, `TSC-USER-001`'s route) now also
  returns `followers_count`, `following_count`, and `is_following` (whether
  the authenticated caller follows this profile). These default to `0`/`0`/
  `false` on the schema so `PATCH /users/me`'s bare
  `UserPrivateProfile.model_validate(user)` construction is unaffected —
  only the profile-lookup route populates real values, via
  `UsersService.get_profile_view`.

## Idempotency contract (human-review focus)

- **Self-follow is impossible, not merely rejected**: `FollowsService`
  compares `current_user.id == target.id` before any database write. This
  check is never a race (it depends only on the caller's own id), so it's
  deterministic — `422 semantic_validation_error` every time, for both
  follow and unfollow.
- **Follow is idempotent**: a repeat follow call for the same pair leaves
  exactly one `follows` row and creates *no* second notification.
  `FollowRepository.follow()` pre-checks `exists()`, then wraps the insert
  in a `SAVEPOINT` (`session.begin_nested()`); a genuine concurrent race —
  two callers both passing the pre-check before either commits — has its
  loser's primary-key violation caught there and treated as "already
  following" rather than propagating and poisoning the caller's outer
  request transaction. `FollowsService.follow()` only calls
  `NotificationsService.create_notification` when `follow()` reports a
  freshly-*created* row, so a repeat/raced call never double-notifies.
- **Unfollow is idempotent**: unfollowing when not following is a no-op,
  not an error, and never creates a notification (unfollow never notifies
  at all — the notification model has no "unfollow" event type).
- **Self-notifications are impossible in two independent places**: the
  self-follow guard above, and `NotificationsService.create_notification`'s
  own `recipient_id == actor.id` no-op guard (`TSC-NOTIF-001`) — a defense
  in depth that would still catch it even if the service-layer check were
  ever removed.

## Follower/following lists

- `FollowRepository.list_followers`/`list_following` return `Follow` edges
  (not `User` rows), cursor-paginated on `(created_at, follower_id)` /
  `(created_at, followee_id)` — the composite key's other half serves as
  the pagination tiebreaker since `follows` has no surrogate `id` column.
- `FollowsService` batch-resolves the referenced `User` rows via
  `UserRepository.get_many`, preserving page order — the same pattern
  `NotificationsService.list_for_recipient` uses to resolve actors
  (`TSC-NOTIF-001`), kept single-table per query rather than a SQL join.
- Cursors round-trip via the shared `app.repositories.pagination` keyset
  helpers, so pages are stable and never repeat/skip a row across calls.

## Rate limiting

- Both `POST` and `DELETE /users/{username}/follow` share one per-user
  sliding-window limit, keyed `follow:{user_id}`, default
  `follow_rate_limit_per_minute = 60` (spec §10.3: "likes/follows
  60/min/user"). Exceeding it returns `429 rate_limited` with a
  `Retry-After` header, matching the existing `check_rate_limit` /
  `RateLimitExceeded` machinery from `TSC-AUTH-001`.
- List endpoints (`/followers`, `/following`) are read-only and not
  rate-limited beyond the global default.

## Verification commands

- `uv run pytest tests/test_follows.py` — full HTTP contract: idempotent
  follow/unfollow, self-follow rejection, 401/404 paths, cursor pagination
  without duplicates, the follow → notification delivery path, rate
  limiting (429 + `Retry-After`), and a concurrent-duplicate-follow-requests
  race settling to exactly one edge and one notification.
- `uv run pytest tests/services/test_follows_service.py` — service-layer
  transactionality: exactly one notification after commit, idempotent
  repeat follow/unfollow, self-follow/not-found errors, follower/following
  resolution and pagination, malformed-cursor rejection.
- `uv run pytest tests/repositories/test_repositories.py -k follow` —
  repository-layer idempotency and pagination, including a genuine
  multi-session concurrency race (5 concurrent `follow()` calls on separate
  connections settle to exactly one row).
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"` —
  full suite (170 tests); `app/repositories/follows.py`,
  `app/routers/follows.py`, `app/schemas/follows.py`, and
  `app/services/follows.py` are all at 100% line coverage.
