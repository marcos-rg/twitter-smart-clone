# Backend

FastAPI + SQLModel project for the Twitter Smart Clone, managed by
[`uv`](https://docs.astral.sh/uv/). See
[specification/specification.md](../specification/specification.md) for the
full architecture and [docs/](../docs) for living documentation.

## Prerequisites

- Python 3.12+ (see [`.python-version`](./.python-version)).
- [`uv`](https://docs.astral.sh/uv/) for dependency management and running
  commands.

## Commands

| Command                              | Description                                  |
| ------------------------------------- | --------------------------------------------- |
| `uv sync`                             | Install dependencies from `uv.lock`.          |
| `uv run uvicorn app.main:app --reload` | Run the dev server at `/api/v1/health`.      |
| `uv run ruff check .`                  | Lint the codebase.                            |
| `uv run black --check .`              | Check formatting.                             |
| `uv run mypy app tests`               | Type-check in strict mode.                    |
| `uv run pytest`                       | Run the test suite.                           |
| `uv run coverage run -m pytest && uv run coverage report` | Run tests with coverage. |

## Project structure

```
app/
├── main.py           # FastAPI app factory
├── core/             # config, security, logging, deps, rate limit
├── models/           # SQLModel tables
├── schemas/           # Pydantic DTOs
├── repositories/      # data access
├── services/          # business logic + authz
├── routers/            # HTTP + WS endpoints
├── ws/                 # ConnectionManager + Redis pub/sub
├── ai/                 # LangChain chains, prompts, guardrails
└── workers/            # Celery app + tasks
alembic/                # migrations
tests/                  # unit + integration + ws
scripts/                # seed, admin CLIs
```
