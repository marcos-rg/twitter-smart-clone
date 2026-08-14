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
- [frontend-profile-search.md](./frontend-profile-search.md) — profile view/edit and search screens, the never-expose-email guarantee, debounced race-safe search, and MSW/Playwright test evidence (`TSC-USER-002`).
- [notifications-backend.md](./notifications-backend.md) — notification list/mark-read APIs, the documented Redis event envelope, the generic post-commit outbox that guarantees rows commit before publication, and verification evidence (`TSC-NOTIF-001`).
- [websocket-realtime.md](./websocket-realtime.md) — authenticated `GET /api/v1/ws` endpoint, the in-process `ConnectionManager`, the Redis pub/sub bridge for cross-process fan-out, heartbeat/reaping, the reconnect contract, and verification evidence (`TSC-NOTIF-004`).
- [follow-graph-backend.md](./follow-graph-backend.md) — idempotent follow/unfollow, follower/following list pagination, profile relationship/count fields, follow rate limiting, and verification evidence (`TSC-SOC-001`).
- [frontend-follow-social.md](./frontend-follow-social.md) — FollowButton (self/followed/unfollowed states), the optimistic follow/unfollow mutation with rollback, follower/following list routes, and MSW/Playwright test evidence (`TSC-SOC-002`).
- [media-upload-backend.md](./media-upload-backend.md) — direct-to-S3/MinIO presigned uploads for avatars/tweet images, the `pending_uploads` ownership/metadata-verification model, randomized object keys, the abandoned-upload cleanup task, and verification evidence against real MinIO (`TSC-MEDIA-001`).
- [frontend-media-upload.md](./frontend-media-upload.md) — the reusable `useImageUploader` state machine, `ImageUploader`/`AvatarUploader` components, the avatar variant wired into profile edit, the injectable adapter seam (real/fake), and component/integration/Playwright test evidence (`TSC-MEDIA-002`).
- [tweet-backend.md](./tweet-backend.md) — tweet creation/retrieval, the approved whitespace policy, the safe-link (never-HTML) contract, flat-reply semantics with an atomic reply/counter/notification transaction, media ordering/ownership re-verification, viewer-state resolution, and profile-timeline/replies pagination, with unit/integration/concurrency test evidence (`TSC-TWEET-001`).
- [frontend-tweet-ui.md](./frontend-tweet-ui.md) — the tweet composer (whitespace/counter contract, embedded image uploader), the safe-link `TweetCard` rendering contract (no `dangerouslySetInnerHTML`), the flat-reply/no-nested-reply UI rule, the tweet-detail/reply screen, direct-cache-write updates on post/reply, and Vitest/Playwright test evidence (`TSC-TWEET-002`).
