# Tweet, reply & profile-timeline backend (TSC-TWEET-001)

Backend slice for tweet creation/retrieval, flat replies, reply counters +
notifications, and profile timelines (spec §5.1 `tweets`/`tweet_media`,
§5.3 counters, §6.3 "Tweets & feed"). Tweet editing/deletion and nested
replies are explicitly out of scope this version.

## API surface

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/tweets` | Create a tweet, or (with `parent_tweet_id`) a flat reply. |
| GET | `/api/v1/tweets/{id}` | Get one tweet. |
| GET | `/api/v1/tweets/{id}/replies` | Flat replies to a tweet, oldest first, cursor-paginated. |
| GET | `/api/v1/users/{username}/tweets` | A user's profile timeline, newest first, cursor-paginated. |

All four render the same `TweetView` shape (`app/schemas/tweets.py`):
`id`, `author` (id/username/name/avatar_key), `content`, `parent_tweet_id`,
`like_count`, `reply_count`, `liked_by_viewer`, `media` (ordered
`{key, content_type, position}`), `links` (`{url, start, end}` spans), and
`created_at`. `TweetsService._to_view_page` batch-resolves authors, media,
and the viewer's like state for a whole page in three queries total,
regardless of page size — no per-row queries.

`GET /users/{username}/tweets` is registered on `app.routers.users` (same
prefix as the rest of `/users/*`) but is built from
`app.routers.tweets.build_tweets_service` — the exact same `TweetsService`
construction the tweets router uses, so all four endpoints render
byte-identical `TweetView` JSON.

## Content validation: the whitespace policy (human-review focus)

`TweetCreateRequest.content` (`app/schemas/tweets.py`) enforces:

- Leading/trailing whitespace (spaces, tabs, newlines) is **stripped**
  before length validation and storage.
- The stripped content must contain **at least one non-whitespace
  character** — a blank or whitespace-only tweet is rejected
  (`422 semantic_validation_error`), not silently stored as an empty row.
- **Internal** whitespace, including newlines, is preserved exactly as
  typed — multi-line tweets are allowed and no run of whitespace is
  collapsed.
- The **1-280 character limit applies to the stripped content**, measured
  in Unicode code points (`len(str)`), consistent with how `bio`/username
  are measured elsewhere in this codebase.

A raw (pre-strip) request body is additionally capped at 2000 characters —
a defensive sanity bound against pathological payloads, not the
authoritative rule (that's the 1-280 check on stripped content).

## Safe link contract (human-review focus)

The backend never returns HTML for tweet content. `content` is always
plain text; `app/services/link_extraction.py`'s `extract_link_entities`
scans it for `http://`/`https://` URLs and returns `(url, start, end)`
character-offset spans as structured JSON (`links` in `TweetView`). The
frontend is expected to render `content` as plain text (React's default
escaping already makes that safe) and overlay real `<a>` elements only at
these server-validated spans — there is no HTML round-trip, so there is
nothing to sanitize on the way out.

Only `http`/`https` schemes are ever recognized:
`javascript:`, `data:`, bare `//scheme-relative`, and every other scheme
are invisible to the URL regex and are additionally rejected by an
explicit `urlsplit().scheme` check, so a link entity can never carry
anything that would let a client `href`-inject script execution.
Trailing sentence punctuation (`.,!?;:'")]}` etc.) typed right after a URL
is trimmed from the match. At most 10 link entities are extracted per
tweet (a defensive cap; a 280-character tweet can't realistically exceed
it).

## Flat-reply semantics (human-review focus)

- **Replies can only target root tweets.** `TweetsService.create_tweet`
  loads the `parent_tweet_id` tweet and rejects it with
  `422 semantic_validation_error` (`CannotReplyToReplyError`) if that
  tweet is itself a reply (`parent.parent_tweet_id is not None`) — the
  service-layer enforcement `app.models.tweet`'s docstring calls for (a
  `CHECK` constraint can't express "does this row's parent have a NULL
  parent" without a subquery).
- **Listing replies of a reply is not an error** — it's always an empty
  page, since no reply can ever have replies. `GET /tweets/{id}/replies`
  only 404s when `{id}` doesn't exist at all.
- **Reply insert + counter increment + notification are one transaction.**
  All three writes go through the same request-scoped `AsyncSession` (no
  early `commit()` in `TweetsService` — only `flush()`), so
  `app.core.deps.get_db_session` commits them together, once, at the end
  of the request.
- **The counter increment is race-safe.**
  `TweetRepository.increment_reply_count` issues a relative SQL
  `UPDATE tweets SET reply_count = reply_count + 1 WHERE id = ...`, not a
  read-modify-write through the ORM. Two overlapping replies to the same
  parent each issue their own atomic increment; PostgreSQL serializes the
  two `UPDATE`s on the row lock, and both increments land — no lost
  update. `tests/test_tweets.py::test_concurrent_replies_to_the_same_tweet_all_land_correctly`
  fires 5 concurrent `POST /tweets` replies (each on its own request-scoped
  session — a genuine cross-connection race) and asserts the parent's
  `reply_count` ends at exactly 5, with exactly 5 replies listed and
  exactly 5 notifications delivered.
- **Self-replies never self-notify** — `NotificationsService.create_notification`'s
  existing `recipient_id == actor.id` no-op guard (`TSC-NOTIF-001`) covers
  replying to your own tweet without any extra check here.

## Media: ordering and ownership

`POST /tweets` accepts `media_keys: list[str]` (0-4 keys, no duplicates),
each the `key` of a previously **confirmed** upload
(`POST /media/presign` → upload → `POST /media/confirm`,
`purpose: "tweet_image"`, `TSC-MEDIA-001`). `TweetsService._verify_media_keys`
re-checks every key server-side, in request order, rejecting the whole
batch (no partial attachment) on the first problem:

1. Not already attached to *any* tweet (`409 conflict` —
   `MediaKeyAlreadyUsedError`; a confirmed key backs at most one tweet,
   ever).
2. A `PendingUpload` row exists for the key (`404 not_found` —
   `MediaKeyNotFoundError`).
3. It belongs to the calling user (`403 forbidden` —
   `MediaKeyForbiddenError`).
4. Its `purpose` is `tweet_image`, not `avatar` (`400 validation_error` —
   `MediaKeyWrongPurposeError`).
5. It's actually `confirmed`, not still `pending` (`400 validation_error` —
   `MediaKeyNotConfirmedError`).

`TweetMedia` rows are inserted with `position` equal to the key's index in
the request list, so `media` in the response is always in the order the
client sent — client-controlled ordering, server-verified ownership.

## Viewer state

`liked_by_viewer` is resolved per-request from `likes` via
`LikeRepository.list_liked_tweet_ids` (batch) / never trusted from the
request. `POST /tweets` (a brand-new tweet) always returns
`liked_by_viewer: false` without a query — a tweet can't be liked before
it exists. The `likes` table and repository predate `TSC-LIKE-001`'s
like/unlike endpoints (they were created by `TSC-DATA-001`); this task only
*reads* them to populate viewer state; wiring `POST/DELETE /tweets/{id}/like`
itself is `TSC-LIKE-001`.

## Pagination

- Timelines (`/users/{username}/tweets`) are newest-first
  (`(author_id, created_at desc)`); replies (`/tweets/{id}/replies`) are
  oldest-first, thread reading order (`(parent_tweet_id, created_at asc)`).
  Both use the shared `app.repositories.pagination` keyset helpers
  (opaque `(created_at, id)` cursor), so pages are stable — no duplicate or
  skipped rows — even when several rows share a timestamp.
- `GET /tweets/{id}/replies` 404s if `{id}` doesn't exist; a malformed
  cursor on any list endpoint returns `400 validation_error`.

## Rate limiting

`POST /tweets` (covers both new tweets and replies — a reply is created
through the same endpoint) is limited per-user, keyed `tweet:{user_id}`,
default `tweet_rate_limit_per_minute = 30` (spec §10.3: "tweet create
30/min/user"), using the existing `check_rate_limit`/`RateLimitExceeded`
machinery from `TSC-AUTH-001`. Exceeding it returns `429 rate_limited` with
a `Retry-After` header.

## Verification commands

- `uv run pytest tests/services/test_link_extraction.py` — pure-function
  unit tests for the safe-link contract: offset correctness,
  `javascript:`/`data:`/scheme-relative rejection, trailing-punctuation
  trimming, the 10-entity cap.
- `uv run pytest tests/services/test_tweets_service.py` — service-layer
  transactionality: reply insert + counter + notification after commit,
  flat-reply rejection, media ownership/confirmation/purpose/reuse checks,
  viewer like state, link entities, reply/timeline pagination and
  malformed-cursor rejection.
- `uv run pytest tests/test_tweets.py` — full HTTP contract: whitespace
  policy (blank/whitespace-only rejected, strip-and-preserve-internal,
  280-char boundary), safe link entities (including an XSS-shaped
  `javascript:`/`data:` payload never becoming a link), media ordering and
  all five media-rejection paths, flat-reply rejection and 404s, reply →
  notification delivery, profile-timeline rendering, pagination without
  duplicates, rate limiting (429 + `Retry-After`), and a 5-way concurrent
  reply race settling to an exactly-correct counter/list/notification
  count.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"` —
  full suite (273 tests); `app/services/tweets.py`,
  `app/routers/tweets.py`, and `app/schemas/tweets.py` are all at 100% line
  coverage.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run ruff check . && uv run ruff format --check . && uv run mypy app tests scripts"` —
  lint/format/type-check clean.
- `curl -s http://localhost:8000/api/v1/openapi.json | python3 -c "import json,sys; print(list(json.load(sys.stdin)['paths']))"` —
  confirms `/api/v1/tweets`, `/api/v1/tweets/{tweet_id}`,
  `/api/v1/tweets/{tweet_id}/replies`, and `/api/v1/users/{username}/tweets`
  are all present in the auto-generated OpenAPI document.
