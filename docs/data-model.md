# Data model, migrations, repositories, and seed data (TSC-DATA-001)

The persistence layer every feature router/service is built on top of: 7
SQLModel table models matching spec §5.1, one hand-written Alembic migration,
an async repository layer with cursor-based keyset pagination, and an
idempotent demo-data seed script/CLI.

> **Addendum (`TSC-MEDIA-001`):** a second migration
> (`alembic/versions/0002_add_pending_uploads.py`) adds an 8th table,
> `pending_uploads` — not part of spec §5.1, but required to safely
> implement §8.4's direct-to-S3/MinIO upload flow. See
> [media-upload-backend.md](./media-upload-backend.md).

## Layout

```
backend/
├── app/
│   ├── models/
│   │   ├── base.py          # UUIDv7 PK + timestamptz column helpers
│   │   ├── user.py           # users (citext username/email, trigram search)
│   │   ├── tweet.py           # tweets (top-level + replies via parent_tweet_id)
│   │   ├── tweet_media.py      # tweet_media (0..4 attachments per tweet)
│   │   ├── follow.py            # follows (composite PK, self-follow CHECK)
│   │   ├── like.py                # likes (composite PK, idempotent insert)
│   │   ├── notification.py         # notifications (native `notification_type` enum)
│   │   └── refresh_token.py         # refresh_tokens (rotation/revocation)
│   ├── core/
│   │   └── security.py       # Argon2id hash_password/verify_password
│   └── repositories/
│       ├── pagination.py    # Cursor/Page + apply_keyset/build_page/clamp_limit
│       ├── base.py           # BaseRepository[ModelT]: get/add/delete/count
│       ├── users.py, tweets.py, follows.py, likes.py, notifications.py,
│       │   refresh_tokens.py, tweet_media.py   # one repo per table
├── alembic/
│   ├── env.py                 # imports app.models, reads Settings.database_url
│   └── versions/0001_initial_schema.py   # hand-written initial migration
├── scripts/
│   ├── factories.py            # deterministic Faker-seeded model builders
│   └── seed.py                  # idempotent CLI: `uv run python -m scripts.seed`
└── tests/repositories/
    ├── conftest.py               # migrated-schema + truncate-then-session fixtures
    ├── test_migrations.py         # round-trip + index/extension existence
    ├── test_constraints.py         # DB-level uniqueness/self-follow/FK rejection
    ├── test_repositories.py         # pagination, idempotent like/follow, notifications
    ├── test_more_coverage.py         # replies/feed pagination, media, delete/count
    └── test_seed.py                   # seed() is idempotent end-to-end
```

## Schema (spec §5.1)

All 7 tables from the spec, each with a client-generated **UUIDv7** primary
key (`app.models.base.new_uuid7`, via `uuid6.uuid7()`) so ids sort
chronologically without a separate index, and `timestamptz` (not bare
`TIMESTAMP`) columns everywhere via `app.models.base.timestamptz_column()`:

- **`users`** — `username`/`email` are PostgreSQL `citext` (case-insensitive
  unique) rather than service-layer `.lower()` tricks. GIN trigram indexes
  (`pg_trgm`, `ix_users_username_trgm`/`ix_users_name_trgm`) back fuzzy
  search via the `%` similarity operator.
- **`tweets`** — self-referencing `parent_tweet_id` distinguishes top-level
  tweets from replies; denormalized `reply_count`/`like_count` counters kept
  in sync by `TweetRepository.increment_reply_count`/`increment_like_count`.
  Composite indexes `(author_id, created_at)`/`(parent_tweet_id, created_at)`
  back the three list shapes (a user's tweets, a thread's replies, and the
  global/home feed).
- **`tweet_media`** — up to 4 attachments per tweet, ordered by `position`
  (`CHECK` constraint bounds `position` to `0..3`).
- **`follows`** — composite `(follower_id, followee_id)` primary key;
  `CHECK (follower_id <> followee_id)` rejects self-follows at the database
  level; unfollow is a plain delete (idempotent: `FollowRepository.unfollow`
  returns whether a row was actually deleted).
- **`likes`** — composite `(user_id, tweet_id)` primary key;
  `LikeRepository.like()` uses `INSERT ... ON CONFLICT DO NOTHING` so liking
  twice is a no-op, not a service-layer race.
- **`notifications`** — `type` is a **native PostgreSQL enum**
  (`notification_type`: `follow`/`like`/`reply`), not free text, so invalid
  values are rejected by the database itself. A partial index
  `(recipient_id) WHERE is_read = false` backs cheap unread counting/listing
  even as read history grows.
- **`refresh_tokens`** — `token_hash` (never the raw token) + `revoked_at`/
  `expires_at`; `RefreshTokenRepository.is_active()` checks both.

Extensions `citext` and `pg_trgm` are created by the migration itself
(`op.execute("CREATE EXTENSION IF NOT EXISTS ...")`).

## Migrations (Alembic, async)

`backend/alembic/env.py` is customized to import `app.models` (registering
every table on `SQLModel.metadata`) and to read `database_url` from
`app.core.config.get_settings()` instead of a static `alembic.ini` value, so
one `DATABASE_URL` env var drives the app, tests, and migrations alike.

The single migration (`0001_initial_schema.py`) is **hand-written, not
autogenerated** — `alembic revision --autogenerate` doesn't reliably emit
`CITEXT`, trigram GIN indexes (`gin_trgm_ops`), partial indexes (`WHERE
is_read = false`), or multi-column `CHECK` constraints, so these needed raw
`op.execute(...)`/explicit `sa.CheckConstraint`/`sa.Index` calls regardless.
`upgrade()`/`downgrade()` are both fully implemented and round-trip tested
(base → head → base → head) against a real Postgres in
`tests/test_migrations.py::test_migration_round_trip_base_to_head_and_back`.

Run migrations with `make migrate` (`docker compose run --rm backend uv run
alembic upgrade head`), matching how CI/the dev stack apply them.

## Repositories (`app/repositories/`)

`BaseRepository[ModelT]` (a PEP 695 generic class) gives every repository
`get`/`add`/`delete`/`count`; each entity repository subclasses it and adds
entity-specific queries (uniqueness lookups, counters, idempotent
insert/delete, cursor pagination).

**Cursor pagination** (`app/repositories/pagination.py`, spec §6.1): the
cursor is an opaque, base64-encoded token round-tripping `(created_at, id)`
of the last item on the previous page — encoding both fields (not just
`created_at`) avoids silently dropping/duplicating rows created in the same
timestamp tick. `clamp_limit()` enforces the spec's default 20 / max 50 page
size. `apply_keyset()` adds the `WHERE (created_at, id) < / > (cursor)`
predicate + `ORDER BY`; `build_page()` fetches `limit + 1` rows so it can
derive `next_cursor` without a separate `COUNT` query.

### SQLModel + async gotchas (see code comments for full detail)

These are the non-obvious pitfalls hit while building this layer, in case
future feature tasks touch this code:

- Always use `sqlmodel.ext.asyncio.session.AsyncSession` (not
  `sqlalchemy.ext.asyncio.AsyncSession`) and `sqlmodel.select` (not
  `sqlalchemy.select`) — only SQLModel's versions make `session.exec(...)`
  return model/scalar instances directly instead of plain `Row` tuples.
- Every `datetime` column must go through `timestamptz_column()`; a bare
  SQLModel `datetime` field maps to `TIMESTAMP WITHOUT TIME ZONE`, which
  rejects the timezone-aware `datetime.now(UTC)` values used everywhere.
- No shared timestamp mixin: a `Field(sa_column=<Column instance>)` can only
  be attached to one `Table`, so a mixin used by multiple `table=True`
  models would make them fight over the same `Column` object. Every model
  calls `timestamptz_column()` itself instead.
- `NotificationType` is a `StrEnum`; the native PostgreSQL enum column uses
  `values_callable=lambda cls: [m.value for m in cls]` so SQLAlchemy binds
  `"follow"`/`"like"`/`"reply"`, not `"FOLLOW"`/`"LIKE"`/`"REPLY"`.
- Without a SQLModel-aware mypy plugin, `Model.column` type-checks as the
  column's plain Python type (e.g. `UUID`, `str`), not a queryable
  `InstrumentedAttribute` — expressions like `.in_(...)`, `.is_(None)`,
  `.op("%")(...)` are correct at runtime but need a narrow, commented
  `# type: ignore[...]` at each call site (see `app/repositories/*.py`).

## Seed data (`scripts/seed.py`, `make seed`)

`uv run python -m scripts.seed` (what `make seed` runs inside the `backend`
container) populates 8 demo users (`scripts/factories.DEMO_PASSWORD` logs
into all of them), a cyclic follow graph, 3 top-level tweets/user, one reply
+ one like per tweet (with matching notifications), all built with a
deterministically-seeded `Faker` instance (`scripts/factories.make_faker`)
so output is stable across runs.

**Idempotent by construction**, not by a blanket "wipe and reinsert":
- Users are looked up by `username` (case-insensitive via `citext`) before
  insert.
- Follows/likes are looked up by their natural composite primary key.
- Tweets have no natural key, so top-level tweet idempotency uses
  `TweetRepository.count_top_level_by_author()` (skip once an author has
  ≥ `TWEETS_PER_USER`), and reply idempotency uses
  `TweetRepository.get_reply_by_author(parent_id, author_id)`.
- Notifications have no database-level natural-key constraint (a real
  re-follow-after-unfollow could legitimately notify twice), so
  `NotificationRepository.exists(...)` is a **seed-script convenience only**,
  not a schema invariant.

Verified via two consecutive runs: the first created `{'users_created': 8,
'follows_created': 16, 'tweets_created': 24, 'replies_created': 24,
'likes_created': 24, 'notifications_created': 64}`; the second created all
zeros. `tests/repositories/test_seed.py` asserts the same behavior
programmatically (calls `scripts.seed.seed()` twice against a truncated DB).

## Testing

`tests/repositories/conftest.py` provides:
- `_migrated_schema` (session-scoped, autouse) — runs `alembic upgrade head`
  once before any test in the suite.
- `db_session` (function-scoped) — `TRUNCATE TABLE ... CASCADE`s every table,
  then yields a fresh `AsyncSession`. **This wipes seed demo data** — re-run
  `make seed` after running this suite if you need it back for manual
  testing.

`TEST_DATABASE_URL` defaults to `DATABASE_URL` (already `postgres:5432`
inside the `backend`/CI container via `docker-compose.yml`), falling back to
`localhost:5432` when neither is set (bare-host runs).

Test files: `tests/repositories/test_migrations.py` (round-trip +
index/extension/constraint existence via `pg_indexes`/`pg_extension`
introspection), `tests/repositories/test_constraints.py` (duplicate
username/email case-insensitivity, self-follow, duplicate follow/like,
orphan-tweet FK rejection), `tests/repositories/test_repositories.py` +
`test_more_coverage.py` (pagination correctness, idempotent like/follow,
notification unread counting, refresh-token rotation/revocation, fuzzy user
search), `tests/repositories/test_seed.py` (seed idempotency), and
`tests/core/test_security.py` (Argon2id password hashing round-trip).

## Verified locally

Run against a clean checkout on Docker 29.5.3 / Compose v5.1.4
(`docker compose -f docker-compose.yml -f docker-compose.dev.yml build backend`
then `up -d postgres redis minio minio-init`):

- `make migrate` (`docker compose run --rm backend uv run alembic upgrade
  head`) — applies `0001_initial_schema` cleanly against a fresh Postgres.
- `make seed` (`docker compose run --rm backend uv run python -m
  scripts.seed`) — first run: `{'users_created': 8, 'follows_created': 16,
  'tweets_created': 24, 'replies_created': 24, 'likes_created': 24,
  'notifications_created': 64}`; second run: all zeros (idempotent). Final
  `psql` counts: 8 users, 48 tweets (24 top-level + 24 replies), 16 follows,
  24 likes, 64 notifications.
- `make lint` (`uv run ruff check .`, `uv run black --check .`, `uv run
  mypy app tests scripts` — `scripts` added to the mypy target list for this
  task — plus the frontend lint/format/typecheck lines) — all pass.
- `make test` (`uv run coverage run -m pytest && uv run coverage report`)
  — **71 passed**, **98%** statement coverage (`fail_under` raised
  80 → 90 in `backend/pyproject.toml`, since this task lands well-tested
  repository/migration/seed code), plus the frontend suite (60 passed).
- `tests/repositories/test_migrations.py::test_migration_round_trip_base_to_head_and_back`
  — base → head → base → head round-trip against the real container Postgres.
- Manual `psql` checks: duplicate username/email (different case) rejected,
  self-follow rejected, duplicate follow rejected, duplicate like rejected —
  all as `IntegrityError`/`CHECK`/unique-violation, not application-level
  checks.
