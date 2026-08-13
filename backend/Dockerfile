# syntax=docker/dockerfile:1.7

# Backend development image (TSC-FOUND-002).
#
# Production hardening (non-root runtime user beyond what's set here, a
# slimmer/no-dev-deps final stage, Gunicorn/Uvicorn worker tuning, etc.) is
# deferred to TSC-OPS-001. Today this Dockerfile only needs to support fast,
# reproducible local development with hot reload.

FROM python:3.12-slim AS base

# Pin the same uv release used by CONTRIBUTING/dev docs so lockfile
# resolution is identical on every machine and in CI.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# ---------------------------------------------------------------------------
# deps: install dependencies only, so this layer is cached across code edits.
# ---------------------------------------------------------------------------
FROM base AS deps

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# ---------------------------------------------------------------------------
# dev: adds the project source and dev dependencies (ruff/black/mypy/pytest);
# used by docker-compose(.dev).yml for the `backend` and `worker` services.
# ---------------------------------------------------------------------------
FROM deps AS dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
