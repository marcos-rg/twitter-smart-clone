# twitter-smart-clone

[![CI](https://github.com/marcos-rg/twitter-smart-clone/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/marcos-rg/twitter-smart-clone/actions/workflows/ci.yml)

A Twitter-like social app: users register, publish short text/image posts
("tweets"), follow each other, reply, like, and get realtime notifications.
It's built as a portfolio/challenge project — the goal is a clean,
well-tested, containerized full-stack app at a modest scale (~100 concurrent
users), not hyperscale production infrastructure. The "smart" part is a
planned LLM-powered assist layer (draft-tweet suggestions, thread summaries)
sitting behind a provider-agnostic backend abstraction — see
[Roadmap](#roadmap) below.

## Current capabilities

- **Auth** — registration, login, JWT access + refresh tokens with rotation,
  protected routes on the frontend.
- **Profiles & search** — view/edit profile (bio, avatar), exact/fuzzy
  username search.
- **Social graph** — follow/unfollow, followers/following lists.
- **Tweets & replies** — compose tweets with up to 4 images, flat (non-nested)
  replies, tweet detail view, per-profile timeline.
- **Feed** — chronological home feed with responsive infinite scroll.
- **Likes** — optimistic like/unlike with rollback on failure.
- **Notifications** — persisted notifications plus realtime delivery over an
  authenticated WebSocket, with an offline/reconnect fallback.
- **Media** — direct-to-MinIO/S3 presigned image uploads (avatars, tweet
  images), validated server-side on confirm.
- **Design system** — a shared component library, exercised in an internal
  `/lab` route (hidden from primary navigation).

Backend: FastAPI + SQLModel + PostgreSQL + Redis + Celery. Frontend: React
18 + Vite + TypeScript. Full stack runs containerized via Docker Compose.
See [`specification/specification.md`](./specification/specification.md) for
the full technical spec and [`specification/tasks.md`](./specification/tasks.md)
for the implementation task list (30 done, 11 to do as of this writing).

## CI & test coverage

The [`CI` workflow](./.github/workflows/ci.yml) runs on every push/PR to
`main`: build both dev images, backend format/lint/type/test
(`ruff`, `black --check`, `mypy`, `pytest` + coverage gate), frontend
format/lint/type/test (`eslint`, `prettier --check`, `tsc`, `vitest` +
coverage gate), a `gitleaks` secret scan, and a Compose smoke test
(build the stack, wait for every service to report healthy, hit the
health/readiness endpoints). The auth E2E job (`Playwright`, three
consecutive full-stack runs) is currently commented out in the workflow.

Coverage measured locally against this branch, same commands CI runs:

| | Statements | Branches | Functions | Lines | Gate |
| --- | --- | --- | --- | --- | --- |
| Backend (`pytest` + `coverage`) | 98% | — | — | 98% | `fail_under = 90` |
| Frontend (`vitest --coverage`) | 91.08% | 84.85% | 88.36% | 92.35% | 50% on all four metrics |

Reproduce locally with `make test` (runs both suites with their coverage
gates inside containers).

## Roadmap

Tracked as tasks in [`specification/tasks.md`](./specification/tasks.md):

- **Notifications** — end-to-end verification of realtime + offline delivery.
- **AI features** — provider-agnostic async LLM backend, tweet-generation and
  thread-summary UI, end-to-end verification.
- **Hardening** — security/abuse-resistance pass, reliability and 100-user
  performance verification.
- **QA** — full-system automated acceptance testing and coverage gates.
- **Ops** — production packaging/deployment stack, release automation,
  backup/rollback.
- **Docs & release** — living documentation pass, v1 release sign-off.

## Running it locally

Requires Docker and Docker Compose.

```bash
git clone <this-repo>
cd twitter-smart-clone
make init
```

`make init` does everything needed for a first run: copies `.env.example`
to `.env` (if missing), builds the images, starts the full stack, waits for
every service to report healthy, applies database migrations, and seeds
demo data (users, tweets, follows, likes, notifications). It's safe to
re-run — the wait/migrate steps are idempotent, and seeding just adds more
demo data.

Once it finishes, the app is at:

| Service | URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Backend health | http://localhost:8000/healthz |
| MinIO console | http://localhost:9001 |

**MinIO / image uploads:** the backend signs presigned upload URLs against
the internal Docker hostname `minio`, which your browser can't resolve on
its own. `make init` prints a reminder for this — add one line to your
hosts file so uploads (avatars, tweet images) work from the browser:

```
127.0.0.1 minio
```

(`/etc/hosts` on macOS/Linux, `C:\Windows\System32\drivers\etc\hosts` on
Windows, may need `sudo`/admin rights to edit.)

### Other `make` targets

Run individually if you don't want the full `make init` flow, or after the
stack is already up:

| Target | Description |
| --- | --- |
| `make up` | Build (if needed) and start the full stack in the background. |
| `make down` | Stop the stack; named volumes (Postgres/Redis/MinIO data) are kept. |
| `make build` | (Re)build the backend and frontend dev images. |
| `make migrate` | Apply database migrations. |
| `make seed` | Populate demo data. |
| `make ps` | Show container status, including health. |
| `make logs` | Follow logs for every service. |
| `make lint` | Run backend + frontend format/lint/type checks inside containers. |
| `make test` | Run backend + frontend test suites (with coverage gates). |
| `make e2e-auth` | Run the Playwright auth E2E suite against a live stack. |

See [docs/local-dev-stack.md](./docs/local-dev-stack.md) for service details,
Compose file layout, and verified bring-up evidence.

## Project structure

```
.
├── backend/              FastAPI + SQLModel API, managed with uv
│   ├── app/
│   │   ├── ai/            LLM abstraction (scaffolded, not yet implemented)
│   │   ├── core/           config, security, storage, middleware, resources
│   │   ├── models/         SQLModel table definitions
│   │   ├── repositories/   data-access layer over the models
│   │   ├── routers/        FastAPI route handlers (one module per resource)
│   │   ├── schemas/        Pydantic request/response shapes
│   │   ├── services/       business logic, orchestrates repositories
│   │   ├── workers/        Celery tasks (counter reconciliation, cleanup)
│   │   └── ws/              WebSocket connection manager + Redis bridge
│   ├── alembic/            database migrations
│   ├── scripts/            one-off scripts (e.g. demo-data seeding)
│   └── tests/               pytest suite, mirrors the app/ layout
├── frontend/              React 18 + Vite + TypeScript SPA
│   └── src/
│       ├── api/             typed HTTP client functions per resource
│       ├── components/      shared/design-system UI components
│       ├── features/        feature modules (auth, tweets, feed, ...)
│       ├── routes/          top-level routed pages
│       ├── stores/          Zustand client-side state
│       └── lib/              small framework-agnostic hooks/utilities
├── docs/                  living documentation, one file per implemented feature
├── specification/         requirements, technical spec, and task tracking
├── scripts/               repo-level helper scripts
├── docker-compose.yml         base stack definition (all services)
├── docker-compose.dev.yml     dev overlay: bind mounts + hot reload
├── docker-compose.e2e.yml     overlay used only by the auth E2E suite
└── Makefile                shared entry point for build/run/lint/test commands
```

See [backend/README.md](./backend/README.md) and
[frontend/README.md](./frontend/README.md) for stack-specific detail.
