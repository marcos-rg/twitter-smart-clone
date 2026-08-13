# Monorepo scaffold (TSC-FOUND-001)

Establishes the typed monorepo skeleton for the Twitter Smart Clone. This
document records what was set up and how to work with it; it does not cover
product features (see later task docs for those).

## Layout

```
twitter-smart-clone/
├── specification/     # upfront planning docs (requirements, spec, tasks)
├── docs/               # this folder — living documentation
├── backend/            # FastAPI + SQLModel API, managed by uv
└── frontend/            # React 18 + Vite + TypeScript SPA
```

## Backend

- **Runtime:** Python 3.12 (pinned via [backend/.python-version](../backend/.python-version)),
  managed by [`uv`](https://docs.astral.sh/uv/).
- **Package layout:** `app/{core,models,schemas,repositories,services,routers,ws,ai,workers}`,
  matching the module boundaries in [specification.md §14](../specification/specification.md).
  Only `app/main.py` (the FastAPI app factory with a `/api/v1/health` endpoint)
  had functional code at this task's scaffold stage; the other packages were
  empty placeholders for later tasks. `app/core`, `app/routers`, and
  `app/workers` gained real content in `TSC-CORE-001` — see
  [backend-platform.md](./backend-platform.md).
- **Dependency management:** `backend/pyproject.toml` + `backend/uv.lock`.
  Runtime deps: `fastapi`, `sqlmodel`, `uvicorn[standard]`. Dev deps: `ruff`,
  `black`, `mypy` (strict mode), `pytest`, `pytest-asyncio`, `httpx`, `coverage`.
- **Commands:** see [backend/README.md](../backend/README.md) for the full list
  (`uv sync`, `uv run ruff check .`, `uv run black --check .`,
  `uv run mypy app tests`, `uv run pytest`).
- **`alembic/`** exists as a placeholder directory; Alembic itself is
  configured in `TSC-DATA-001` once the first models exist.

## Frontend

- **Runtime:** Node.js 24 (see [frontend/.nvmrc](../frontend/.nvmrc)), npm 11+.
- **Stack:** React 18 + Vite 8 + TypeScript (strict mode), ESLint (flat config)
  + Prettier, Vitest + React Testing Library for unit/component tests,
  Playwright for e2e.
- **Package layout:** `src/{api,components,features,stores,routes,lib}` plus
  `main.tsx`/`App.tsx`, matching [specification.md §14](../specification/specification.md).
  The feature folders are placeholders (`.gitkeep`) until later tasks add
  code.
- **Commands:** see [frontend/README.md](../frontend/README.md) for the full
  list (`npm ci`, `npm run typecheck`, `npm run lint`, `npm run format:check`,
  `npm run test`, `npm run build`, `npm run e2e`).

## Verified locally

Commands below were run against a clean checkout (fresh `.venv` /
`node_modules`) and all passed:

- Runtimes: Python 3.14.6 (system) / Python 3.12.11 (uv-managed, project
  pinned), `uv` 0.12.1, Node.js v24.12.0, npm 11.6.2.
- Backend: `uv sync`, `uv run ruff check .`, `uv run black --check .`,
  `uv run mypy app tests`, `uv run coverage run -m pytest && uv run coverage report`
  (100% statement coverage on the scaffold).
- Frontend: `npm ci` (0 vulnerabilities), `npm run typecheck`,
  `npm run lint`, `npm run format:check`, `npm run test`, `npm run build`.

## Notes / decisions

- The default `create-vite` React 19 + oxlint template was retargeted to
  React 18 + ESLint/Prettier to match the approved stack in
  [specification.md §3](../specification/specification.md).
- `vite`/`vitest` versions were bumped past the template defaults to the
  latest stable releases to clear known `npm audit` advisories (path
  traversal / dev-server file disclosure); the project now installs with
  zero reported vulnerabilities.
- Container images (`Dockerfile`s), `docker-compose.yml`, and CI workflows are
  out of scope for this task and are covered by `TSC-FOUND-002` and
  `TSC-FOUND-003`.
