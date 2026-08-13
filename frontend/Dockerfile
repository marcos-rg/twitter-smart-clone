# syntax=docker/dockerfile:1.7

# Frontend development image (TSC-FOUND-002).
#
# The production image (multi-stage build -> Nginx static stage per
# specification.md §12.2) is deferred to TSC-OPS-001. Today this Dockerfile
# only needs to support fast, reproducible local development with Vite's
# hot module reload.

FROM node:24-alpine AS base

WORKDIR /app

# ---------------------------------------------------------------------------
# deps: install dependencies only, so this layer is cached across code edits.
# ---------------------------------------------------------------------------
FROM base AS deps

COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
# dev: adds the project source; used by docker-compose(.dev).yml for the
# `frontend` service, running Vite's dev server with HMR.
# ---------------------------------------------------------------------------
FROM deps AS dev

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
