# Home-feed backend (TSC-FEED-001)

Fan-out-on-read home feed: `GET /api/v1/feed` (spec §6.3 "Tweets & feed",
§8.2 "Feed generation (fan-out on read)"). Renders the exact same `TweetView`
shape as `POST /tweets`, `GET /tweets/{id}`, `GET /tweets/{id}/replies`, and
`GET /users/{username}/tweets` (`app/schemas/tweets.py`) — a tweet looks
identical wherever it's fetched from.

## API surface

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/feed` | Home feed: caller's own tweets + tweets from users they follow, newest first, cursor-paginated. |

Query params: `cursor` (opaque, from a previous page's `page.next_cursor`),
`limit` (`1..50`, default `20`, `422` above 50 — same contract as every
other list endpoint in this codebase, `app/repositories/pagination.py`). A
malformed `cursor` returns `400 validation_error`.

## Own-tweets inclusion (human-review focus)

The approved product rule: **a user's home feed includes their own
tweets**, in addition to tweets from everyone they follow — matching
mainstream "home timeline" behavior. `TweetsService._feed_author_ids` builds
the author set as `[viewer.id, *followee_ids]`. This is the specific
decision `TSC-FEED-001`'s human review gate calls out for approval; the spec
text itself ("queries tweets authored by the set of users the requester
follows") is silent on self-inclusion.

## Author-set resolution

`FollowRepository.list_followee_ids(user_id)` returns the caller's *entire*
following set unpaginated (`SELECT followee_id FROM follows WHERE
follower_id = :user_id`, no keyset) — the feed needs the whole set for a
single `author_id IN (...)` predicate, unlike the paginated
followers/following list endpoints. `TweetRepository.list_feed` (already
present from `TSC-TWEET-001`) then does the actual keyset-paginated
`WHERE author_id IN (...) ORDER BY created_at DESC, id DESC LIMIT n+1` read.

## Pagination & tie-breaking

Same opaque `(created_at, id)` keyset cursor as every other list endpoint
(`app/repositories/pagination.py`): encodes the last row's `(created_at,
id)`, and orders by `(created_at DESC, id DESC)` so two tweets created in
the same timestamp tick still get a stable, total order — no duplicate or
skipped row across pages, verified under both a synthetic identical-timestamp
tie (`tests/services/test_feed_service.py::test_feed_breaks_ties_deterministically_for_identical_timestamps`)
and a genuine concurrent-insert race
(`tests/test_feed.py::test_feed_has_no_duplicate_or_missing_items_under_concurrent_inserts`,
10 concurrent `POST /tweets` calls, feed walked page-by-page afterward with
per-page duplicate assertions).

## Caching (human-review focus)

Spec §8.2: *"A short-TTL Redis cache may cache the first page per user for a
few seconds to smooth infinite-scroll refreshes."* Implemented in
`TweetsService.list_feed`:

- **Only the first page** (`cursor is None`) of a given `(viewer, limit)`
  shape is ever cached. Every later page, and every request once the entry
  has expired, reads live from PostgreSQL.
- **Cache key:** `feed:{viewer_id}:{clamped_limit}` — scoped to the
  requesting user's id, so a cache hit can never serve one user's feed to
  another (`tests/services/test_feed_service.py::test_feed_cache_is_isolated_per_user`).
- **TTL:** `Settings.feed_cache_ttl_seconds` (default `5`; `0` disables
  caching entirely). Expiry is a plain Redis `EX` — no explicit read-your-
  own-write staleness handling beyond that TTL window
  (`tests/services/test_feed_service.py::test_feed_first_page_is_served_from_cache_within_ttl`,
  `::test_feed_cache_expires_after_ttl`).
- **No active invalidation.** A new tweet from a followee does **not** purge
  every follower's cached first page — the TTL is short enough that a page
  is never stale for long, and invalidating on every tweet write would
  reintroduce the fan-out-on-write cost this design deliberately defers
  (spec §8.2: "Suitable for this scale; fan-out-on-write is deferred").
  `tests/test_feed.py::test_feed_first_page_is_cached_briefly_and_isolated_per_user`
  demonstrates the smoothing behavior this buys: a tweet posted immediately
  after a cached read doesn't appear until the entry expires/is bypassed.

## Query shape & N+1 avoidance

`TweetsService._to_view_page` (shared with every other tweet-listing
endpoint) batch-resolves a whole page's authors, media, and the viewer's
like state in three queries total, regardless of page size — never one
query per row. For the feed specifically that's 5 queries total per
uncached request: `list_followee_ids`, the feed's own keyset `SELECT`,
`users.get_many`, `tweet_media.list_for_tweets`,
`likes.list_liked_tweet_ids`.
`tests/services/test_feed_service.py::test_feed_page_resolves_authors_media_and_likes_in_a_fixed_query_count`
asserts this holds (`<= 5` SQL statements) for a 15-tweet page with media
attached to every tweet, via a `before_cursor_execute` SQLAlchemy event
counter.

## Indexes / query plan

No new migration: `ix_tweets_created_at` (`created_at DESC`, added by the
initial schema migration for exactly this purpose) backs the feed's
`author_id IN (...) ORDER BY created_at DESC, id DESC` query.
`tests/repositories/test_feed_query_plan.py` seeds ~20 followed authors ×
150 tweets + 50 unrelated authors × 150 tweets (5,000 rows) and asserts
(with `enable_seqscan = off` to force Postgres to reveal the *next-best*
plan if the intended index weren't usable) that `EXPLAIN` shows an
`Index Scan using ix_tweets_created_at`, never a `Seq Scan`:

```
Limit
  ->  Incremental Sort
        Sort Key: created_at DESC, id DESC
        Presorted Key: created_at
        ->  Index Scan using ix_tweets_created_at on tweets
              Filter: (author_id = ANY ('{...20 uuids...}'::uuid[]))
```

## Verification commands

- `uv run pytest tests/services/test_feed_service.py` — membership (own +
  followed, excludes non-followed), ordering/pagination/tie-breaking, limit
  default/clamp, malformed-cursor rejection, fixed query-count (N+1),
  and cache isolation/expiry/first-page-only scope.
- `uv run pytest tests/test_feed.py` — full HTTP contract: auth
  requirement, membership, empty feed, `limit>50` → `422`, malformed
  cursor → `400`, pagination without duplicates/skips, a 10-way concurrent
  insert race with no duplicate/missing items across pages, and cache
  isolation/short-TTL smoothing behavior.
- `uv run pytest tests/repositories/test_feed_query_plan.py` — `EXPLAIN`
  evidence that the feed query uses `ix_tweets_created_at`, not a
  sequential scan, at a representative data volume.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"` —
  full suite (293 tests, was 273 before this task); `app/services/tweets.py`,
  `app/repositories/follows.py`, and `app/routers/feed.py` are all at 100%
  line coverage; total project coverage 98% (gate: 90%).
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run ruff check . && uv run ruff format --check . && uv run mypy app tests scripts"` —
  lint/format/type-check clean.
- `curl -s http://localhost:8000/api/v1/openapi.json | python3 -c "import json,sys; print('/api/v1/feed' in json.load(sys.stdin)['paths'])"` —
  confirms `/api/v1/feed` is present in the auto-generated OpenAPI document.
