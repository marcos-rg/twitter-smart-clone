# twitter-smart-clone

this is a twitter clone with LLM capabilities

## Structure

- [`specification/`](./specification) — requirements, specification, and task tracking.
- [`docs/`](./docs) — living application documentation.
- [`backend/`](./backend) — FastAPI + SQLModel API, managed with `uv`. See [backend/README.md](./backend/README.md).
- [`frontend/`](./frontend) — React 18 + Vite + TypeScript SPA. See [frontend/README.md](./frontend/README.md).

## Local development

The full local stack (API, worker, frontend, PostgreSQL, Redis, MinIO) runs
via Docker Compose:

```bash
cp .env.example .env   # first time only
make up                # build + start everything, with hot reload
```

See [docs/local-dev-stack.md](./docs/local-dev-stack.md) for service URLs,
all `make` targets, and verified bring-up evidence.
