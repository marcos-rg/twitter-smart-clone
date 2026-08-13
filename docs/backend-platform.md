# Backend application platform (TSC-CORE-001)

The shared FastAPI platform every feature router/service is built on top of:
app factory, typed settings, async resource lifecycle, API
versioning/OpenAPI, request correlation, structured logging, the standard
error envelope, security headers, and CORS. No product endpoints live here —
those are added by feature tasks (`TSC-DATA-001` onward) on top of this
foundation.

## Layout

```
backend/app/
├── main.py             # create_app() factory; wires everything below
├── core/
│   ├── config.py        # pydantic-settings Settings (env-driven, 12-factor)
│   ├── resources.py     # async Postgres/Redis/MinIO lifecycle + readiness checks
│   ├── middleware.py     # RequestContextMiddleware, SecurityHeadersMiddleware
│   ├── errors.py         # AppError + standard error envelope + handlers
│   └── logging.py        # structlog JSON configuration
├── routers/
│   └── health.py          # /healthz, /readyz
└── workers/
    └── celery_app.py       # shared Celery app (Redis broker/result backend)
```

## Settings (`app.core.config.Settings`)

A single `pydantic-settings` `BaseSettings` class reads every configuration
value from the environment (falling back to the same local-dev defaults as
`.env.example`/`docker-compose.yml`, so the app boots without a `.env`
file). Notable fields:

- `database_url`, `redis_url`, `minio_endpoint`/`minio_bucket` — connection
  strings for the three async resources below.
- `minio_access_key`/`minio_secret_key` — read from the `MINIO_ROOT_USER`/
  `MINIO_ROOT_PASSWORD` env vars (aliased; the same MinIO root credentials
  `minio-init` uses to create the bucket also authenticate the app's S3
  client in dev/test).
- `cors_allowed_origins` — accepts a comma-separated string from
  `CORS_ALLOWED_ORIGINS` (e.g. the `.env.example` default
  `http://localhost:5173`) and parses it into a list.
- `celery_broker_url`/`celery_result_backend` — optional; default to
  `redis_url` when unset (`effective_celery_broker_url`/
  `effective_celery_result_backend`).
- `environment`/`is_production` — drives whether HSTS is sent (see below).

`get_settings()` is an `lru_cache`d accessor for use as a dependency; the app
factory (`create_app`) also accepts an explicit `Settings` instance so tests
can construct isolated configurations.

## Async resource lifecycle (`app.core.resources`)

`build_resources(settings)` creates, once per process:

- **PostgreSQL** — an async SQLAlchemy engine (`asyncpg` driver) +
  `async_sessionmaker`, pooled per `database_pool_size`/`database_max_overflow`.
- **Redis** — `redis.asyncio.Redis.from_url(...)`.
- **MinIO/S3** — an `aioboto3` async S3 client pointed at `minio_endpoint`,
  authenticated with the MinIO root credentials.

All three are lazy: creating them never opens a real connection, so the app
starts (and reports liveness) even if a dependency is temporarily down.
`AppResources.aclose()` releases every resource; `create_lifespan(settings)`
wraps `build_resources`/`aclose` in a FastAPI `lifespan`, storing the result
on `app.state.resources` for `/readyz` (and, later, request-scoped
dependencies) to use.

`check_database`/`check_redis`/`check_object_storage` each run one cheap
round-trip (`SELECT 1`, `PING`, `HEAD` the bucket) under a bounded
`asyncio.timeout` and return `True`/`False` — never raise — so `/readyz`
degrades gracefully instead of hanging or 500ing when a dependency is down.

## API versioning, docs, and health endpoints

- OpenAPI/Swagger UI are served under the versioned prefix:
  `/api/v1/openapi.json`, `/api/v1/docs` (spec §6: `Base URL: /api/v1`).
- `/healthz` — liveness. Always `200 {"status": "ok"}`; never touches a
  dependency, so it can't be blocked by a slow/down Postgres, Redis, or MinIO.
- `/readyz` — readiness. Runs all three dependency checks concurrently and
  returns `200 {"status": "ready", "checks": {...}}` only if every one
  succeeds, else `503 {"status": "not_ready", "checks": {...}}` with the
  per-dependency detail (`"ok"` / `"unavailable"`).

Both health endpoints are intentionally **not** versioned under `/api/v1` —
they're operational/orchestration endpoints (Kubernetes-style probe
convention), not part of the public API contract.

## Standard error envelope (`app.core.errors`)

Every error response is shaped like spec §6.2 (RFC-9457-inspired):

```json
{
  "error": {
    "code": "not_found",
    "message": "Tweet not found.",
    "details": null,
    "request_id": "3c7765a2-6d45-47c3-bf5e-ffb02a0b9f61"
  }
}
```

- `AppError` — base class for feature/service-layer domain errors
  (`raise AppError("Username is already taken.", code="conflict",
  status_code=409, details=[...])`); use this instead of a bare
  `HTTPException` whenever the `code` shouldn't just be derived from the
  HTTP status.
- `HTTPException` (FastAPI's own, or manually raised) is mapped to a stable
  `code` per status (`400`→`validation_error`, `401`→`unauthenticated`,
  `403`→`forbidden`, `404`→`not_found`, `409`→`conflict`,
  `422`→`semantic_validation_error`, `429`→`rate_limited`,
  `500`→`internal_error`); any `headers` on the exception (e.g.
  `Retry-After` on a `429`) are forwarded.
- `RequestValidationError` (FastAPI/Pydantic request validation) → `422`
  with a `details` list of `{"field": ..., "issue": ...}`.
- Any other exception → `500`, generic message, full traceback logged
  server-side only (never leaked to the client).

`request_id` always matches the `X-Request-ID` response header and the
`request_id` field on the access-log line for the same request.

## Request context, logging, and security headers (`app.core.middleware`, `app.core.logging`)

- **`RequestContextMiddleware`** reuses an inbound `X-Request-ID` header or
  generates a UUID4, stores it on `request.state.request_id`, binds
  `request_id`/`method`/`path` to `structlog`'s contextvars for the request,
  and logs one `request_completed` JSON line (with `status_code` and
  `duration_ms`) when it finishes. It also converts any exception that
  escapes the router into the standard `500` envelope itself — see the
  middleware ordering note below for why.
- **`configure_logging`** configures `structlog` to render every log line as
  a single JSON object on stdout, with a redaction processor that masks
  well-known secret field names (`password`, `authorization`, `token`,
  `cookie`, etc.) as a defense-in-depth backstop.
- **`SecurityHeadersMiddleware`** sets `Content-Security-Policy`,
  `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options` on
  every response; `Strict-Transport-Security` is only added when
  `settings.is_production` (sending HSTS over a plain-HTTP local origin
  would make browsers force HTTPS on subsequent requests to that host).

### Middleware ordering

`app.main.create_app` adds middleware in this order — `RequestContextMiddleware`,
then `CORSMiddleware`, then `SecurityHeadersMiddleware` — which (because
Starlette wraps in *reverse* add-order) produces this actual request flow:

```
client → SecurityHeaders → CORS → RequestContext → ExceptionMiddleware → router
```

This matters for one specific reason: Starlette always wraps the **entire**
stack — including every middleware above — in its own `ServerErrorMiddleware`,
so a `500` response built by a handler registered for the bare `Exception`
type would skip CORS and the security headers entirely. `RequestContextMiddleware`
therefore catches unhandled exceptions itself and returns the standard error
envelope directly, so that response still flows back out through CORS and
`SecurityHeadersMiddleware` like any other response. `app.core.errors.unhandled_exception_handler`
is still registered as a defensive backstop for the (normally unreachable)
case of an exception escaping outside `RequestContextMiddleware`'s scope.

## CORS

`CORSMiddleware` is configured from `settings.cors_allowed_origins`
(`allow_credentials=True`, so the SPA's httpOnly refresh cookie is sent on
cross-origin requests) and exposes the `X-Request-ID` header to browser JS.
Requests from an origin not in the configured list receive no
`Access-Control-Allow-*` headers, so browsers block the response from
reading it.

## Celery (`app.workers.celery_app`)

`celery_app` is configured with the Redis broker/result backend (JSON
serialization, UTC, `task_track_started=True`). No tasks are defined yet —
feature tasks (AI generation, notification fan-out) register their own
`@celery_app.task`s on top of this shared instance. The `worker` compose
service runs `celery -A app.workers.celery_app worker --loglevel=info`
against it; `beat` (periodic tasks) is deferred until a task actually needs
scheduling.

## Testing

`backend/tests/conftest.py` provides `test_settings` (a fixed, known
configuration) and `unreachable_settings` (endpoints on a guaranteed-closed
loopback port, `127.0.0.1:1`) fixtures. `unreachable_settings` exists because
the default `postgres`/`redis`/`minio` hostnames are unreachable on a bare
host but **are** reachable inside the docker-compose network (where
`make test`/CI actually run this suite, via Docker's embedded DNS resolving
them to the real, healthy containers) — tests asserting the "dependency
unavailable" path use `unreachable_settings` so they're deterministic in
both environments.

Test files: `tests/core/test_config.py`, `tests/core/test_resources.py`,
`tests/core/test_middleware.py`, `tests/core/test_errors_backstop.py`,
`tests/test_errors.py`, `tests/test_health.py`, `tests/test_cors.py`,
`tests/test_security_headers.py`, `tests/test_logging.py`,
`tests/test_main.py`, `tests/workers/test_celery_app.py`.

## Verified locally

Run against a clean checkout on Docker 29.5.3 / Compose v5.1.4 (`docker
compose -f docker-compose.yml -f docker-compose.dev.yml build backend worker`
then `up -d`; all six services reported `healthy`/running):

- `uv run ruff check .`, `uv run black --check .`, `uv run mypy app tests`,
  and `uv run coverage run -m pytest && uv run coverage report` — all pass,
  46 tests, **100%** statement coverage (`fail_under` raised from 60 → 80 in
  `backend/pyproject.toml`, matching the spec's final backend coverage
  target). Re-ran the same four commands inside the `backend` container
  (`docker compose ... run --rm backend ...`, i.e. `make lint`/`make test`)
  with identical results.
- `curl http://localhost:8000/healthz` → `{"status":"ok"}`.
- `curl http://localhost:8000/readyz` → `{"status":"ready","checks":{"database":"ok","redis":"ok","object_storage":"ok"}}`
  (HTTP 200) against the real Postgres/Redis/MinIO containers.
- `docker compose ... stop redis`, then `curl http://localhost:8000/readyz`
  → HTTP **503**, `{"status":"not_ready","checks":{...,"redis":"unavailable",...}}`;
  `docker compose ... start redis`, then the same request → HTTP 200 again.
- `curl -H "Origin: http://localhost:5173" http://localhost:8000/healthz`
  → `access-control-allow-origin: http://localhost:5173` and
  `access-control-allow-credentials: true` present; the same request with
  `Origin: http://evil.example.com` → no `access-control-allow-origin`
  header.
- `curl -H "Authorization: Bearer <your-token-here>" http://localhost:8000/healthz`,
  then inspected the `backend` container logs — one JSON
  `request_completed` line with `request_id`/`method`/`path`/`status_code`/
  `duration_ms`, and the raw token string does not appear anywhere in the
  logs.
- `curl http://localhost:8000/api/v1/openapi.json` → valid OpenAPI document
  listing `/healthz` and `/readyz`.
- `make lint` and `make test` (backend + frontend) both pass end-to-end.
