# Local container development stack (TSC-FOUND-002)

Docker Compose brings up the full local stack — API, worker, frontend,
PostgreSQL 16, Redis 7, and MinIO — with hot reload and persistent
development data. Production hardening (TLS, non-dev images, Gunicorn
tuning, `docker-compose.prod.yml`, etc.) is deferred to `TSC-OPS-001`.

## Quick start

```bash
cp .env.example .env   # first time only; edit values if you need to
make up                # builds images (if needed) and starts everything
```

`make up` runs:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Once containers report healthy (see `make ps`), the stack is reachable at:

| Service            | Host URL                          | Container-to-container address |
| ------------------ | ---------------------------------- | ------------------------------- |
| Frontend (Vite)    | http://localhost:5173              | `http://frontend:5173`          |
| Backend API health | http://localhost:8000/api/v1/health | `http://backend:8000`          |
| PostgreSQL         | `localhost:5432`                    | `postgres:5432`                 |
| Redis              | `localhost:6379`                    | `redis:6379`                    |
| MinIO API          | http://localhost:9000              | `http://minio:9000`             |
| MinIO console       | http://localhost:9001              | —                                |

Stop everything with `make down` (named volumes, and therefore Postgres,
Redis, and MinIO data, are preserved across `make down` / `make up`).

## Makefile targets

| Target         | Description |
| -------------- | ----------- |
| `make up`      | Build (if needed) and start the full stack in the background. |
| `make down`    | Stop the stack; named volumes are kept. |
| `make build`   | (Re)build the backend and frontend dev images. |
| `make ps`      | Show container status, including health. |
| `make logs`    | Follow logs for every service. |
| `make lint`    | Run backend (`ruff`, `black --check`, `mypy`) and frontend (`eslint`, `prettier --check`, `tsc`) checks inside containers. |
| `make test`    | Run backend `pytest` and frontend `vitest` inside containers. |
| `make seed`    | Placeholder — the seed CLI lands with `TSC-DATA-001`. |
| `make migrate` | Placeholder — Alembic is configured with `TSC-DATA-001`. |

`lint`/`test` deliberately run through `docker compose run`, not on the
host, so the same checks are guaranteed to run identically for every
contributor and in CI (`TSC-FOUND-003`).

## Compose file layout

- **`docker-compose.yml`** — base stack definition. Declares every service
  (`postgres`, `redis`, `minio`, `minio-init`, `backend`, `worker`,
  `frontend`), health checks, named volumes, and non-secret default
  environment values (`${VAR:-default}`) so `docker compose config` and
  `docker compose up` both work on a clean checkout with **no `.env` file
  present**.
- **`docker-compose.dev.yml`** — development overlay. Bind-mounts backend
  (`app/`, `tests/`, `scripts/`, `alembic/`, `pyproject.toml`) and frontend
  (`src/`, `tests/`, `e2e/`, `public/`, `index.html`, `vite.config.ts`)
  source directories into the running containers so `uvicorn --reload` and
  Vite HMR pick up host edits without an image rebuild. A named volume is
  mounted over `/app/.venv` (backend) and `/app/node_modules` (frontend) so
  the dependencies installed at image build time are used, rather than
  whatever the host machine may or may not have installed — Docker
  populates a fresh named volume with the image's directory contents the
  first time it is mounted, so this does not require re-running `uv sync`
  / `npm ci` after start-up.
- Always run both files together (`make up`/`make lint`/`make test` do
  this automatically). Running only `docker-compose.yml` starts a working
  stack too, just without host bind-mounts (edits require a rebuild).

## Services

- **`postgres`** — `postgres:16-alpine`, healthcheck via `pg_isready`,
  data in the `postgres_data` named volume.
- **`redis`** — `redis:7-alpine` with `--appendonly yes`, healthcheck via
  `redis-cli ping`, data in the `redis_data` named volume.
- **`minio`** — `minio/minio:latest` (S3-compatible object storage),
  healthcheck via `curl .../minio/health/live`, data in the `minio_data`
  named volume.
- **`minio-init`** — one-shot `minio/mc` job that waits for `minio` to be
  healthy, then creates the `twitter-smart-clone-media` bucket
  (`mc mb --ignore-existing`, safe to rerun). It is not part of the
  "stack is healthy" signal — only the long-running `minio` service is.
- **`backend`** — built from `backend/Dockerfile` (`dev` target); runs
  `uvicorn app.main:app --reload`; healthcheck hits
  `/api/v1/health`; depends on `postgres`/`redis`/`minio` being healthy.
- **`worker`** — same image as `backend`, run with a placeholder command.
  Celery isn't wired up yet — that lands in `TSC-CORE-001` — so this
  service currently just idles to establish the compose topology described
  in `specification.md` §12.1 ahead of time.
- **`frontend`** — built from `frontend/Dockerfile` (`dev` target); runs
  `vite --host 0.0.0.0`; healthcheck does an HTTP GET against `/`.

## Dockerfiles

Both `backend/Dockerfile` and `frontend/Dockerfile` are multi-stage and
dev-focused right now:

- `backend/Dockerfile`: `base` (Python 3.12-slim + pinned `uv` binary) →
  `deps` (installs locked dependencies only, cached across code edits) →
  `dev` (adds project source + dev dependency group, `CMD` runs
  `uvicorn --reload`).
- `frontend/Dockerfile`: `base` (Node 24-alpine) → `deps` (`npm ci`,
  cached across code edits) → `dev` (adds project source, `CMD` runs
  `vite --host 0.0.0.0`).

Neither Dockerfile has a production/Nginx stage yet; that is explicitly
in scope for `TSC-OPS-001`.

## Environment variables

`.env.example` documents every variable (Postgres, Redis, MinIO, backend,
frontend) with non-secret local-development defaults. Copy it to `.env`
(git-ignored) before running the stack; the same defaults are also baked
into `docker-compose.yml` via `${VAR:-default}` substitution so the stack
still starts without a `.env` file (e.g., for a first `docker compose
config` check on a clean checkout).

## Verified locally

Commands below were run against a clean checkout (`docker compose down -v`
beforehand) on Docker 29.5.3 / Compose v5.1.4:

- `docker compose -f docker-compose.yml config` — succeeds (exit 0), no
  secret values present (only local dev-only defaults).
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config`
  — succeeds (exit 0).
- `make up` — builds `backend`/`frontend` images and starts all 6 long-running services (plus the one-shot `minio-init` job);
  `postgres`, `redis`, `minio`, `backend`, and `frontend` report `healthy`
  within 30 seconds on a truly clean checkout (fresh volumes, freshly
  built images, verified via `docker volume rm` + `docker rmi` beforehand);
  `worker` remains running (no healthcheck) and `minio-init` exits 0 after creating the bucket.
- API health: `curl http://localhost:8000/api/v1/health` →
  `{"status":"ok"}`.
- Frontend: `curl -o /dev/null -w '%{http_code}' http://localhost:5173/` →
  `200`.
- Container-to-container reachability confirmed by executing inside the
  `backend` container (`socket.create_connection` to `postgres:5432`,
  `redis:6379`, `minio:9000`) and inside the `frontend` container (HTTP GET
  to `http://backend:8000/api/v1/health`) — all succeed without relying on
  host-published ports.
- Hot reload confirmed both ways: touching `backend/app/main.py` triggers
  `WatchFiles detected changes ... Reloading...` in the `backend` logs;
  touching `frontend/src/App.tsx` triggers a `[vite] (client) hmr update`
  log line in the `frontend` logs — both without an image rebuild.
- `make lint` — `ruff check`, `black --check`, `mypy app tests` (backend)
  and `eslint`, `prettier --check`, `tsc -b --noEmit` (frontend) all pass
  inside the containers.
- `make test` — backend `pytest` (1 passed) and frontend `vitest run`
  (1 passed) both pass inside the containers.
- Data persistence: wrote a row to Postgres and a key to Redis, ran
  `make down` then `make up` again — both values were still present
  afterwards, and `minio-init` re-running `mc mb --ignore-existing`
  exited 0 (idempotent, bucket already existed).
- `make seed` / `make migrate` intentionally print an informative
  placeholder message and exit 0; the seed CLI and Alembic wiring are
  delivered by `TSC-DATA-001`, out of scope here.

## Notes / decisions

- The `worker` service reuses the `backend` image (same Dockerfile,
  `dev` target) rather than a separate Dockerfile, matching how a Celery
  worker typically shares its codebase with the API. It runs a placeholder
  command until `TSC-CORE-001` adds a real Celery app.
- `docker-compose.yml` alone (without the `dev` overlay) is also a valid,
  fully working way to start the stack — it just won't hot-reload on host
  edits, since no source directories are bind-mounted.
- CI workflows that exercise this stack (integration smoke tests, image
  builds) are added by `TSC-FOUND-003`, not here.
