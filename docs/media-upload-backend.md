# Media upload backend (TSC-MEDIA-001)

Direct-to-S3/MinIO image uploads for avatars and (future) tweet images,
using presigned URLs and server-side confirmation (spec §8.4). The API
process never receives or proxies image bytes: it only ever hands out a
presigned `PUT` URL and later checks what actually landed in the bucket.

There is no `Tweet`/`tweet_media` row to attach uploads to yet
(`TSC-TWEET-001`, which depends on this task, creates that). Presign/confirm
are therefore generic — parameterized by a `purpose` (`avatar` or
`tweet_image`) — rather than hard-wired to `users.avatar_key` alone; when
`TSC-TWEET-001` lands, tweet creation calls
`MediaService.confirm_keys(purpose="tweet_image", keys=[...])` (or the
already-confirmed keys from a prior `/media/confirm` call) instead of
re-implementing this validation.

## Flow

```
1. POST /api/v1/media/presign  { purpose, files: [{content_type, size_bytes}, ...] }
   -> { uploads: [{ key, upload_url, content_type, expires_at }, ...] }

2. Client PUTs each file's bytes directly to its upload_url (MinIO/S3).
   The API process is not in this request path at all.

3a. POST /api/v1/media/confirm  { purpose, keys: [...] }         (generic; tweet images)
3b. POST /api/v1/users/me/avatar  { key }                        (avatar; also sets avatar_key)
```

`/api/v1/media/presign` and `/api/v1/media/confirm` are the generic pair
spec §6.3 calls out (`POST /media/presign`); `POST /api/v1/users/me/avatar`
is spec §6.3's dual-purpose avatar row ("Get presigned upload URL; confirm
sets `avatar_key`") — implemented here as **confirm-only** (`{"key": ...}`),
with presigning done through the generic `/media/presign` endpoint
(`purpose: "avatar"`) rather than a second, avatar-specific presign route.

## `pending_uploads`: the record behind every presigned URL

Not part of spec §5.1's entity list — a bookkeeping table this task adds
(`app.models.pending_upload.PendingUpload`) because confirming a key safely
requires answering three questions the client's say-so can't be trusted
for: *did this user actually request this key*, *what did they declare
about it*, and *has it already been confirmed*.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users.id | who requested the presign |
| purpose | enum(`avatar`, `tweet_image`) | |
| s3_key | text UNIQUE | the randomized object key |
| content_type | text | declared at presign time |
| size_bytes | bigint | declared at presign time |
| status | enum(`pending`, `confirmed`) | |
| presign_expires_at | timestamptz | when the presigned URL itself expires |
| created_at / confirmed_at | timestamptz | |

A row is created `pending` at presign time and flipped to `confirmed` once
`MediaService.confirm_keys` verifies the object. Migration:
`backend/alembic/versions/0002_add_pending_uploads.py`.

## Object keys: randomized, user-scoped, no client input

`app.core.storage.build_object_key(user_id, purpose, content_type)` builds
`{purpose}/{user_id}/{uuid4}{ext}` — e.g.
`avatar/018f2b3e-.../4a1c9e2b6f3a4e2caa6e1e2b7a9c0f11.png`. The only
client-supplied input reflected in the key is the (already-validated)
content-type's extension; the filename stem is a fresh `uuid4` every call.
This is what makes path traversal and guessable/colliding overwrites
structurally impossible — there's no code path that lets a client's string
end up in the key — and, combined with `pending_uploads.user_id`, is what
makes "confirm a key owned by another user" a checkable condition rather
than something the key's shape alone would need to encode.

## Validation

**At presign** (`MediaService.presign_batch`, all-or-nothing per batch):

- `content_type` ∈ `{image/png, image/jpeg, image/webp}`
  (`app.models.tweet_media.ALLOWED_CONTENT_TYPES`) — else `400
  unsupported_media_type`.
- `size_bytes` ≤ `Settings.media_max_image_bytes` (default 5 MiB) — else
  `400 media_too_large`.
- File count ≤ `Settings.media_max_tweet_images` (default 4) for
  `purpose=tweet_image`, or exactly 1 for `purpose=avatar` — else `400
  too_many_media_files`. There's no tweet row yet to count images against,
  so the cap applies to the presign/confirm request batch itself — a
  client presigns/confirms the images for one tweet together.

**At confirm** (`MediaService.confirm_keys`, all-or-nothing per batch):

- Every key must have a `pending_uploads` row (`404` `not_found` otherwise
  — "confirm a key nobody ever presigned").
- `pending_uploads.user_id` must equal the caller (`403 forbidden`
  otherwise — "confirm a key owned by another user").
- `pending_uploads.purpose` must match the confirm call's `purpose` (`400`).
- The row must not already be `confirmed` (`409 conflict` — confirm is not
  re-confirmable).
- `ObjectStorage.head_object(key)` must return metadata — `None` (object
  never uploaded) raises `400 media_object_missing`.
- The object's **actual** `content_type`/`content_length` (from
  `HeadObject`) must equal what was declared at presign time, and the
  actual size must still be within the limit — any mismatch raises `400
  media_metadata_mismatch` ("altered metadata": the client swapped in a
  different file after getting the presigned URL). MinIO/S3 itself already
  rejects a `PUT` whose `Content-Type` header doesn't match what was signed
  into the URL (`ObjectStorage.presign_put` binds `ContentType` into the
  signature) — the confirm-time check is a second, independent line of
  defense on top of that, not the only one.

Confirming an avatar (`MediaService.confirm_avatar`, used by `POST
/api/v1/users/me/avatar`) runs the same `confirm_keys` check for a single
`purpose=avatar` key, then sets `user.avatar_key` and flushes — the value
is present on both the confirm response and any subsequent `GET
/api/v1/users/{username}` / `GET /api/v1/auth/me` read.

## Storage abstraction

`app.core.storage.ObjectStorage` wraps the `aioboto3` S3 client already
built by `app.core.resources.build_resources` (shared with the readiness
check, `TSC-CORE-001`) behind three async methods — `presign_put`,
`head_object`, `delete_object` — declared as the `SupportsObjectStorage`
protocol so `MediaService` is testable against a fake/in-memory
implementation (`tests/services/test_media_service.py::FakeStorage`)
without touching MinIO. `StorageError` wraps any unexpected
`botocore.exceptions.ClientError` (or the "MinIO unreachable" case) so
callers depend on one exception type, not `botocore`'s; `head_object`
returning `None` (object doesn't exist — the ordinary case for a
never-completed upload) is deliberately distinct from `StorageError`
(storage itself is broken).

## Abandoned-upload cleanup

`app.workers.media_cleanup.cleanup_abandoned_uploads` (a Celery task) sweeps
`pending_uploads` rows still `pending` after
`Settings.media_abandoned_upload_ttl_hours` (default **24 hours**),
best-effort deletes whatever object (if any) landed at that key, then
deletes the row. A storage-delete failure is logged and the row is still
reaped — the alternative (leaving it `pending` to retry forever) means a
permanently-broken key wedges the sweep indefinitely.

`docker-compose.yml` currently runs a `worker` container but no `beat`
container (`TSC-CORE-001`'s "beat (periodic tasks) is deferred" note) —
adding scheduled execution is out of this task's scope. `celery_app.py`
registers an inert `beat_schedule` entry (hourly) so wiring an actual
`beat` service later is a one-line infra change. Until then, run it
manually or from an external cron:

```bash
docker compose run --rm backend uv run celery -A app.workers.celery_app \
  call app.workers.media_cleanup.cleanup_abandoned_uploads
```

## API surface

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/media/presign` | Presigned `PUT` URL(s) for one or more files (`purpose: avatar\|tweet_image`). |
| POST | `/api/v1/media/confirm` | Confirm previously presigned keys were actually uploaded. |
| POST | `/api/v1/users/me/avatar` | Confirm an avatar upload; sets the caller's `avatar_key`. |

All three require authentication (`get_current_user`) and are scoped to the
caller by construction.

## Configuration (`app.core.config.Settings`)

| Setting | Default | Notes |
|---|---|---|
| `media_max_image_bytes` | 5 MiB | Per-file size limit (spec §8.4: "~5MB each"). |
| `media_max_tweet_images` | 4 | Per-batch file count for `purpose=tweet_image` (spec §8.4: "max 4 images/tweet"). |
| `media_presign_expires_seconds` | 300 | Presigned `PUT` URL lifetime. |
| `media_abandoned_upload_ttl_hours` | 24 | Age at which a still-`pending` row is reaped. |

**These four values, plus the cleanup task's behavior on storage failure,
are the human-review focus for this task** (upload limits and
abandoned-upload behavior) — see the task's human review gate.

## Verification evidence

Run from the repo root:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  uv run alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  uv run pytest tests/core/test_storage.py tests/services/test_media_service.py \
    tests/test_media.py tests/workers/test_media_cleanup.py -q
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  sh -c "uv run coverage run -m pytest && uv run coverage report"
```

As of this task: 220 tests pass (51 of them new/media-specific), overall
backend coverage 98% (`app/core/storage.py`, `app/models/pending_upload.py`,
`app/repositories/pending_uploads.py`, `app/schemas/media.py`,
`app/services/media.py`, `app/routers/media.py`,
`app/workers/media_cleanup.py` all at 100%).

- **PNG/JPEG/WebP round trip**: `tests/test_media.py::test_presign_upload_confirm_tweet_image_round_trip`
  (parametrized over all three) presigns, `PUT`s real bytes straight to
  MinIO, then confirms.
- **Avatar persists across a fresh read**:
  `test_confirm_avatar_updates_profile_and_survives_fresh_read` confirms,
  then separately calls `GET /api/v1/auth/me` and `GET
  /api/v1/users/{username}`.
- **Rejections**: unsupported type, oversized file, >4 tweet images (all at
  presign); object never uploaded, altered metadata, key owned by another
  user, unknown key (all at confirm) — one test each in `tests/test_media.py`
  and mirrored against a fake storage double in
  `tests/services/test_media_service.py`.
- **API never proxies image bytes**:
  `test_api_request_bodies_never_carry_image_bytes` asserts the presign/
  confirm JSON request bodies stay under 1KB even when the declared file
  size is 4MB (no bytes are ever attached), and every round-trip test
  asserts the presigned `upload_url`'s host is `minio`, not the API.
- **Presigned URL expiry**: `test_presigned_url_expires` presigns with a
  1-second expiry, waits, then shows MinIO itself rejects the late `PUT`
  (`>=400`).
- **Object keys prevent path traversal/guessable overwrites**:
  `tests/core/test_storage.py::TestBuildObjectKey` (scoping, no `..`,
  uniqueness across 50 calls).
- **Storage integration + failure paths against MinIO**: every test above
  runs against the real `minio` container; `tests/core/test_storage.py`
  additionally mocks `ClientError`/connection failures per storage method,
  and `tests/workers/test_media_cleanup.py::test_cleanup_still_deletes_row_when_storage_delete_fails`
  mocks a delete failure during cleanup.
- **Example confirmed-object metadata** (from
  `test_presign_upload_confirm_tweet_image_round_trip`, `image/png` case):
  `{"key": "tweet_image/<user_id>/<uuid4>.png", "content_type": "image/png", "size_bytes": 108}`.

```bash
cd backend && uv run ruff check . && uv run black --check . && uv run mypy app tests scripts
```
All pass with no errors.
