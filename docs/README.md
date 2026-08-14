# Documentation

This folder holds the **actual, living documentation** of the application (architecture notes, setup guides, module/API docs, ADRs, etc.) as it gets built.

It is distinct from [`specification/`](../specification/), which contains the upfront planning docs (requirements and specification) that guided the initial design.

## Contents

- [monorepo-scaffold.md](./monorepo-scaffold.md) — backend/frontend project scaffold, tooling, and verified setup commands (`TSC-FOUND-001`).
- [local-dev-stack.md](./local-dev-stack.md) — Docker Compose local development stack (API, worker, frontend, PostgreSQL, Redis, MinIO), Makefile targets, and verified bring-up commands (`TSC-FOUND-002`).
- [design-system.md](./design-system.md) — Tailwind design tokens, core UI components, responsive app shell, and the `/lab` component interaction lab with accessibility and responsive evidence (`TSC-UX-001`).
- [backend-platform.md](./backend-platform.md) — shared FastAPI app platform: typed settings, async PostgreSQL/Redis/MinIO/Celery lifecycle, API versioning/OpenAPI, request IDs, structured logging, the standard error envelope, security headers, CORS, and verification evidence (`TSC-CORE-001`).
- [data-model.md](./data-model.md) — PostgreSQL schema (SQLModel), Alembic migrations, async repositories with cursor pagination, and the idempotent demo-data seed script/CLI (`TSC-DATA-001`).
- [frontend-auth.md](./frontend-auth.md) — register/login/logout, in-memory access token + httpOnly refresh cookie handling, session restoration, protected/public route guards, single-flight 401 refresh, and MSW/Playwright test evidence (`TSC-AUTH-002`).
- [user-profile-search-backend.md](./user-profile-search-backend.md) — public profiles, self-editing, profile timeline contract, exact/prefix/fuzzy user search, cursor/error behavior, and verification commands (`TSC-USER-001`).
