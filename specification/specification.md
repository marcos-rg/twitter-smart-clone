# Twitter Smart Clone — Technical Specification

> **Status:** Draft v0.1 — Blueprint for the whole project
> **Source of truth for requirements:** [requirements.md](./requirements.md)
> This document translates the functional and non-functional requirements into concrete, buildable engineering decisions. Where the requirements are silent, decisions here were made explicitly and are called out.

## Table of Contents

1. [Project definition](#1-project-definition)
2. [Scope](#2-scope)
3. [Stack selection](#3-stack-selection)
4. [System architecture](#4-system-architecture)
5. [Data model](#5-data-model)
6. [API design & contract](#6-api-design--contract)
7. [Auth & authorization](#7-auth--authorization)
8. [Backend details](#8-backend-details)
9. [Frontend details](#9-frontend-details)
10. [Cross-cutting concerns](#10-cross-cutting-concerns)
11. [AI details](#11-ai-details)
12. [DevOps details](#12-devops-details)
13. [Testing strategy](#13-testing-strategy)
14. [Project structure](#14-project-structure)
15. [Good practices](#15-good-practices)

---

## 1. Project definition

A Twitter-like social application ("Twitter Smart Clone") where users register, publish short text/image/link posts ("tweets"), follow other users, interact through likes and flat replies, receive real-time notifications, and use LLM-powered helpers to draft tweets and summarize threads.

**Nature of the project:** Challenge. It is explicitly **not** production scale — the target is correctness, clean architecture, and demonstrable best practices at a modest concurrency level (~100 concurrent users), not hyperscale.

**Primary goals**
- Demonstrate a well-structured, tested, containerized full-stack application.
- Deliver a responsive, mobile-first UX with real-time interactions.
- Integrate LLM features behind a provider-agnostic abstraction.

**Success criteria**
- All in-scope functional requirements implemented and demonstrable end-to-end.
- Backend test coverage ≥ 80%, frontend ≥ 70%.
- Real-time notifications delivered within 2s while the recipient is online.
- Full local bring-up with a single `docker compose up` plus a seed script.

---

## 2. Scope

### 2.1 In scope

**Authentication**
- Register, log in, log out.
- Email + password as the only login method.
- Protection of private routes and per-user data.

**User profiles**
- View and edit own profile: name, username, email, profile picture (placeholder by default), bio.
- View other users' public profiles.

**Tweets**
- Create tweets (text up to 280 characters).
- Tweets may contain text, images, and links.
- Home feed: chronological, infinite scroll, tweets from followed users.

**Social interactions**
- Follow / unfollow users.
- Like / unlike tweets.
- Flat replies (no nested threads).
- Like and reply counts per tweet.
- Followers / following lists per user.
- A user's own tweets list (profile timeline).
- User search by name or username: exact, prefix, and fuzzy match.
- Real-time notifications for new followers, likes, and replies — delivered within 2s over WebSocket when online, persisted for later viewing when offline.

**LLM features**
- Generate a tweet draft via LLM.
- Generate a summary of a thread (a tweet + its replies) via LLM.

**Non-functional (in scope)**
- ~100 concurrent users without significant degradation.
- Password hashing + salting; API rate limiting; protection against SQLi/XSS/CSRF; per-user access control; structured logging.
- Mobile-first responsive design (breakpoints: mobile `<640px`, tablet `640–1024px`, desktop `>1024px`).
- Clear error messages; intuitive UI; animations/transitions.
- Unit + integration + e2e tests; coverage targets above.
- Seed script; Docker for dev + deploy; tests runnable in Docker; CI/CD pipeline; semantic versioning via git tags.

### 2.2 Out of scope

- **Tweet deletion** — explicitly out of scope for now (deferred; see §2.3). The data model reserves room for it but no delete endpoint/UI ships in this version.
- Editing tweets after posting.
- Nested/threaded replies (replies are flat only).
- Direct messages / private chat.
- Retweets / quote tweets / bookmarks.
- Hashtags, trends, and topic discovery feeds.
- Private accounts and follower approval (all accounts are public — see §7).
- Block / mute / report (deferred — see §2.3).
- OAuth / social login, 2FA, email verification, password reset flows.
- Push/email/mobile notifications (only in-app + WebSocket notifications are in scope).
- Media beyond images (video, GIF galleries, polls).
- Admin/moderation console, analytics dashboards.
- Horizontal autoscaling, multi-region, Kubernetes.

### 2.3 Deferred (planned, not in this version)

- **Tweet deletion** (soft vs hard delete decision to be made when picked up).
- **Block & report** users/tweets. The schema is designed so these can be added without migration pain.
- Error tracking service (e.g., Sentry) and metrics/dashboards (Prometheus/Grafana/Loki) — logging is JSON-structured now so these plug in later.
- Fan-out-on-write timeline caching (only needed if scale grows past this project's target).
- Email verification & password reset.

---

## 3. Stack selection

| Layer | Choice | Notes |
|---|---|---|
| Backend language | **Python 3.12+** | Hard requirement. It's my main programming language. |
| Backend package manager | **uv** | Dependency resolution, virtualenv management, and lockfile (`uv.lock`); replaces pip/Poetry. |
| Backend framework | **FastAPI** | Async, first-class WebSocket + OpenAPI. |
| ASGI server | **Uvicorn** (managed by Gunicorn workers in prod) | |
| ORM | **SQLModel** | Pydantic + SQLAlchemy core; typed models. |
| Migrations | **Alembic** | Versioned schema migrations. |
| Database | **PostgreSQL 16** | Relational core; `pg_trgm` for fuzzy search. |
| Cache / broker / pub-sub | **Redis 7** | Rate limiting, WebSocket fan-out, caching, Celery broker. |
| Background jobs | **Celery** (Redis broker/result backend) | LLM calls, notification fan-out. |
| Object storage | **S3-compatible** — MinIO (local/dev), AWS S3 (prod) | Profile pics + tweet images. |
| LLM orchestration | **LangChain suite**, provider-agnostic | Swap providers via config. |
| Frontend framework | **React 18 + Vite + TypeScript** | SPA. |
| Styling | **Tailwind CSS** | Mobile-first utility CSS. |
| Server state / data fetching | **TanStack Query** | Caching, pagination, invalidation. |
| Client state | **Zustand** | Lightweight global state. |
| Real-time | **Native WebSocket** (FastAPI server, browser client) | Redis pub-sub for cross-worker fan-out. |
| Auth | **JWT access + refresh**, refresh in httpOnly cookie | See §7. |
| Containerization | **Docker + Docker Compose** | Dev + deploy. |
| CI/CD | **GitHub Actions** | Lint, test, build, tag-based release. |
| Deployment target | **Single VPS + Docker Compose** | Portfolio-scale. |
| Logging | **Structured JSON logs** | Error tracking deferred. |

**Testing tools:** `pytest` + `pytest-asyncio` + `httpx` + `coverage` (backend); `Vitest` + `React Testing Library` (frontend unit/integration); `Playwright` (e2e). All runnable inside Docker.

---

## 4. System architecture

### 4.1 High-level components

```
                         ┌──────────────────────────────┐
        Browser (SPA) ── │  React + Vite + TS (Nginx)    │
          │  HTTPS/WSS   └──────────────┬───────────────┘
          │                             │ REST + WebSocket
          ▼                             ▼
   ┌─────────────────────────────────────────────────────┐
   │              FastAPI (Uvicorn/Gunicorn)              │
   │  Routers · Services · Auth · WS manager · Rate limit │
   └───┬───────────────┬───────────────┬─────────────┬────┘
       │               │               │             │
       ▼               ▼               ▼             ▼
 ┌──────────┐   ┌────────────┐   ┌───────────┐  ┌──────────┐
 │PostgreSQL│   │   Redis    │   │ S3/MinIO  │  │  Celery  │
 │  (data)  │   │cache/pub-  │   │  (media)  │  │  worker  │
 │          │   │sub/rate/br │   │           │  │  + beat  │
 └──────────┘   └─────┬──────┘   └───────────┘  └────┬─────┘
                      │  pub/sub                      │
                      └───────────── LLM provider ◄───┘
                                    (LangChain)
```

- **Frontend**: static SPA served by Nginx; talks to the API over REST and to the WebSocket endpoint for real-time events.
- **API (FastAPI)**: stateless HTTP + WebSocket app; runs as multiple Uvicorn workers behind Gunicorn.
- **PostgreSQL**: system of record.
- **Redis**: rate-limit counters, cache, Celery broker/result backend, and pub/sub channel for cross-worker WebSocket fan-out.
- **Celery worker + beat**: async LLM generation, notification creation/fan-out, and periodic maintenance.
- **S3/MinIO**: media blob storage; API issues presigned URLs.

### 4.2 Real-time / WebSocket design

**Endpoint:** `GET /ws` (upgraded to WebSocket). Auth via short-lived access token passed as a query param or `Sec-WebSocket-Protocol` and validated on connect. Unauthenticated upgrades are rejected.

**Connection lifecycle**
1. Client obtains an access token (from login/refresh) and opens `wss://.../ws?token=<jwt>`.
2. Server validates the JWT, registers the connection in an in-process `ConnectionManager` keyed by `user_id` (a user may have multiple connections/tabs).
3. Server subscribes the process to the Redis channel `notifications:{user_id}` (per-user) — or a single `notifications` channel with user routing — so events published by any worker reach the worker holding the socket.
4. Heartbeat: server sends `ping` every 30s; client replies `pong`. Idle/broken sockets are reaped.

**Event delivery flow (e.g., a like)**
1. `POST /tweets/{id}/like` writes the like, then enqueues/handles a notification.
2. Notification is **persisted** to the `notifications` table (so offline users see it later).
3. The service `PUBLISH`es a JSON event to Redis channel for the recipient.
4. Whichever worker holds that recipient's socket receives the pub/sub message and pushes it down the WebSocket. Target end-to-end latency **< 2s** while online.
5. If the recipient has no active socket, the persisted notification is delivered on next fetch / next connect.

**Message envelope (server → client)**
```json
{
  "type": "notification",
  "event": "like | reply | follow",
  "data": { "notification_id": "...", "actor": {...}, "tweet_id": "...", "created_at": "..." }
}
```

**Delivery semantics:** at-least-once via persistence + live push; the client de-duplicates by `notification_id`. WebSocket is a delivery accelerator, not the source of truth — the DB is.

**Scaling note:** In-process connection registry + Redis pub/sub allows multiple API workers/instances. No sticky sessions required because any worker can publish; only the worker(s) holding a given socket deliver.

### 4.3 Transport decision: WebSocket vs SSE (trade-off note)

The notification requirement is strictly **server → client** (the client performs all actions — likes, follows, replies — over normal REST, never over the realtime channel). That one-way pattern could be served equally well by **Server-Sent Events (SSE)**, so the choice was evaluated explicitly.

| Factor | SSE (`text/event-stream`) | **WebSocket (chosen)** |
|---|---|---|
| Direction needed | Server → client only — exact fit | Full duplex (more than currently needed) |
| Protocol / infra | Plain HTTP; trivial through Nginx | Requires `Upgrade`/`Connection` proxy config |
| Reconnect | Built into browser `EventSource` + `Last-Event-ID` replay | Implement reconnect/backoff manually |
| Auth | `EventSource` can't set headers ⇒ token via cookie/query | Token via query param / subprotocol on connect |
| Heartbeat/backpressure | Simple (keepalive comments) | Manual ping/pong |
| FastAPI support | Via `StreamingResponse` (more manual) | First-class `@app.websocket` |
| Redis fan-out | Identical | Identical |
| Future duplex features (DMs, typing, presence) | Would need replacing | Already supported |

**Why WebSocket is kept:** it keeps the door open for future upgrades — such as direct messaging, typing indicators, and presence — without a transport rewrite, and FastAPI's first-class WebSocket support keeps the implementation clean. Even though the current notification need is one-way, choosing the duplex transport now avoids re-architecting the realtime layer later.

**When SSE would be preferable:** if we optimized purely for the current one-way need, SSE is simpler and gives free browser reconnection + event replay (which complements the "persist for offline" guarantee). It remains a low-risk drop-in alternative because the Redis pub/sub fan-out design above is transport-agnostic — only the client transport and the endpoint handler would change.

**Scale note (either transport):** at ~100 concurrent users (one stream each) connection limits are a non-issue. The only SSE-specific caveat — the ~6-connections-per-domain cap on HTTP/1.1 — disappears under HTTP/2 and is irrelevant at this scale.

---

## 5. Data model

PostgreSQL. All tables use `bigint`/`uuid` primary keys (**UUIDv7** preferred for time-sortable ids), `created_at`/`updated_at` timestamps (UTC), and appropriate indexes. Fuzzy user search uses the `pg_trgm` extension.

### 5.1 Entities

**users**
| column | type | notes |
|---|---|---|
| id | uuid PK | UUIDv7 |
| name | text | display name |
| username | citext UNIQUE | case-insensitive; validated `^[a-zA-Z0-9_]{3,30}$` |
| email | citext UNIQUE | login identifier |
| password_hash | text | Argon2id hash (includes salt) |
| bio | text NULL | max 160 chars |
| avatar_key | text NULL | S3 object key; NULL ⇒ placeholder |
| created_at / updated_at | timestamptz | |

Indexes: `UNIQUE(username)`, `UNIQUE(email)`, GIN trigram index on `username` and `name` for search.

**tweets**
| column | type | notes |
|---|---|---|
| id | uuid PK | UUIDv7 (chronological ordering) |
| author_id | uuid FK → users.id | |
| content | text | max 280 chars (validated) |
| parent_tweet_id | uuid FK → tweets.id NULL | non-NULL ⇒ this is a flat reply |
| like_count | int default 0 | denormalized counter |
| reply_count | int default 0 | denormalized counter |
| created_at | timestamptz | |
| deleted_at | timestamptz NULL | reserved for deferred deletion; unused this version |

Indexes: `(author_id, created_at desc)`, `(parent_tweet_id, created_at asc)`, `(created_at desc)`.
Constraint: a reply cannot have a reply — enforced in the service layer (a tweet whose `parent_tweet_id` is non-NULL cannot itself be a parent).

**tweet_media**
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| tweet_id | uuid FK → tweets.id | |
| s3_key | text | object key |
| content_type | text | image/png, image/jpeg, image/webp |
| position | int | ordering (0..3) |

**follows**
| column | type | notes |
|---|---|---|
| follower_id | uuid FK → users.id | |
| followee_id | uuid FK → users.id | |
| created_at | timestamptz | |

PK: `(follower_id, followee_id)`. Constraint: `follower_id <> followee_id`. Indexes on both columns.

**likes**
| column | type | notes |
|---|---|---|
| user_id | uuid FK → users.id | |
| tweet_id | uuid FK → tweets.id | |
| created_at | timestamptz | |

PK: `(user_id, tweet_id)` (idempotent like). Index on `tweet_id`.

**notifications**
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| recipient_id | uuid FK → users.id | |
| actor_id | uuid FK → users.id | who triggered it |
| type | enum(`follow`,`like`,`reply`) | |
| tweet_id | uuid FK → tweets.id NULL | for like/reply |
| is_read | boolean default false | |
| created_at | timestamptz | |

Indexes: `(recipient_id, created_at desc)`, partial index on `(recipient_id) WHERE is_read = false`.

**refresh_tokens** (rotation + revocation)
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users.id | |
| token_hash | text | hash of the refresh token |
| expires_at | timestamptz | |
| revoked_at | timestamptz NULL | |
| created_at | timestamptz | |

### 5.2 Relationships (ER summary)

- `users 1—* tweets` (author)
- `tweets 1—* tweets` (self-referential flat reply via `parent_tweet_id`, depth = 1)
- `tweets 1—* tweet_media`
- `users *—* users` via `follows`
- `users *—* tweets` via `likes`
- `users 1—* notifications` (recipient), `users 1—* notifications` (actor)

### 5.3 Counters & consistency

- `like_count` and `reply_count` are denormalized for read performance and updated in the same transaction as the like/reply insert. A periodic Celery task can reconcile counters as a safety net.

---

## 6. API design & contract

- **Base URL:** `/api/v1`
- **Format:** JSON only; `Content-Type: application/json` (media upload via presigned S3 URLs, see §8.4).
- **Auth:** `Authorization: Bearer <access_token>` for protected routes; refresh via httpOnly cookie (see §7).
- **OpenAPI:** auto-generated by FastAPI at `/api/v1/docs` and `/api/v1/openapi.json`.
- **Versioning:** URL-based (`/v1`).

### 6.1 Pagination (cursor / keyset)

All list endpoints use **cursor-based keyset pagination** (stable for chronological infinite scroll).

Request: `?limit=20&cursor=<opaque>` (`limit` default 20, max 50).
The cursor is a base64-encoded, opaque token encoding `(created_at, id)` of the last item.

Response envelope:
```json
{
  "data": [ /* items */ ],
  "page": {
    "next_cursor": "eyJ0cyI6..."   // null when no more pages
  }
}
```

### 6.2 Error format

Uniform error body (RFC-9457-inspired):
```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary.",
    "details": [
      { "field": "content", "issue": "must be at most 280 characters" }
    ],
    "request_id": "01J..."
  }
}
```
Conventions:
- `code` is a stable machine string; `message` is user-safe.
- `request_id` echoes the per-request correlation id (also in logs and the `X-Request-ID` header).
- HTTP status: `400` validation, `401` unauthenticated, `403` forbidden, `404` not found, `409` conflict, `422` semantic validation, `429` rate limited (includes `Retry-After`), `500` internal.

### 6.3 Endpoint catalog (v1)

**Auth**
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create account. |
| POST | `/auth/login` | Email+password ⇒ access token (body) + refresh cookie. |
| POST | `/auth/refresh` | Rotate refresh cookie ⇒ new access token. |
| POST | `/auth/logout` | Revoke refresh token, clear cookie. |
| GET | `/auth/me` | Current user. |

**Users & profiles**
| Method | Path | Description |
|---|---|---|
| GET | `/users/{username}` | Public profile. |
| PATCH | `/users/me` | Edit own profile (name, username, email, bio). |
| POST | `/users/me/avatar` | Get presigned upload URL; confirm sets `avatar_key`. |
| GET | `/users/{username}/tweets` | User's tweets (paginated). |
| GET | `/users/{username}/followers` | Followers list (paginated). |
| GET | `/users/{username}/following` | Following list (paginated). |
| GET | `/users/search?q=&mode=exact\|prefix\|fuzzy` | Search users. |

**Follows**
| Method | Path | Description |
|---|---|---|
| POST | `/users/{username}/follow` | Follow. |
| DELETE | `/users/{username}/follow` | Unfollow. |

**Tweets & feed**
| Method | Path | Description |
|---|---|---|
| POST | `/tweets` | Create tweet (text, optional media keys, optional `parent_tweet_id`). |
| GET | `/tweets/{id}` | Get a tweet. |
| GET | `/tweets/{id}/replies` | Flat replies (paginated). |
| GET | `/feed` | Home feed from followed users (cursor paginated). |
| POST | `/tweets/{id}/like` | Like (idempotent). |
| DELETE | `/tweets/{id}/like` | Unlike. |
| POST | `/media/presign` | Presigned upload URL for tweet images. |

> **Note:** No `DELETE /tweets/{id}` in v1 — tweet deletion is out of scope (§2.2).

**Notifications**
| Method | Path | Description |
|---|---|---|
| GET | `/notifications` | List (paginated), newest first. |
| POST | `/notifications/read` | Mark all/selected as read. |
| WS | `/ws` | Real-time notification stream (see §4.2). |

**AI**
| Method | Path | Description |
|---|---|---|
| POST | `/ai/generate-tweet` | Generate a tweet draft from a prompt. |
| POST | `/ai/summarize-thread` | Summarize a tweet + its replies. |

Long-running AI calls return `202 Accepted` with a `job_id`; the client polls `GET /ai/jobs/{job_id}` or receives a WebSocket event on completion (Celery-backed).

---

## 7. Auth & authorization

### 7.1 Authentication

- **Method:** email + password only.
- **Password hashing:** Argon2id (salted; via `passlib`/`argon2-cffi`).
- **Tokens:**
  - **Access token** — JWT, short-lived (15 min), returned in the login/refresh response body, kept in memory on the client (not localStorage).
  - **Refresh token** — opaque/long-lived (e.g., 7 days), stored **httpOnly + Secure + SameSite=Strict cookie**; server stores only its hash in `refresh_tokens`.
- **Rotation:** every `/auth/refresh` issues a new refresh token and revokes the old one (reuse detection ⇒ revoke the whole family).
- **Logout:** revokes the refresh token and clears the cookie.

### 7.2 Authorization

- All accounts are **public** (v1): any authenticated user can view any profile and any user's tweets, follow anyone, and like/reply to any tweet. (Private accounts are out of scope; block/report deferred.)
- **Ownership rules** (enforced server-side, per request):
  - Only the owner may edit their profile / avatar.
  - Replies and likes are attributed to the authenticated user.
  - Notifications are readable only by their `recipient_id`.
- **Route protection:** a FastAPI dependency validates the access token and injects the current user; protected routers depend on it. WebSocket connections validate the token on connect.
- **Object-level checks** live in the service layer (never trust client-supplied user ids).

---

## 8. Backend details

### 8.1 Layering

```
routers/      → HTTP & WS endpoints, request/response schemas (Pydantic)
services/     → business logic, authorization, transactions
repositories/ → data access (SQLModel queries)
models/       → SQLModel table definitions
schemas/      → Pydantic DTOs (request/response)
core/         → config, security, logging, dependencies, rate limiting
workers/      → Celery tasks
ws/           → ConnectionManager, Redis pub/sub bridge
ai/           → LangChain chains, prompt templates, guardrails
```

- **Async-first:** async SQLModel/SQLAlchemy sessions, async httpx for outbound calls.
- **Transactions:** service methods wrap multi-write operations (e.g., like + counter + notification) in a single DB transaction; the WebSocket publish happens after commit.
- **Validation:** Pydantic enforces field limits (280-char tweet, 160-char bio, username regex, allowed image content-types).

### 8.2 Feed generation (fan-out on read)

- `/feed` queries tweets authored by the set of users the requester follows, ordered by `created_at desc`, keyset-paginated. Suitable for this scale; fan-out-on-write is deferred.
- A short-TTL Redis cache may cache the first page per user for a few seconds to smooth infinite-scroll refreshes.

### 8.3 Search

- `pg_trgm` GIN indexes on `users.username` and `users.name`.
- `mode=exact` ⇒ equality (case-insensitive); `mode=prefix` ⇒ `ILIKE 'q%'` (index-assisted); `mode=fuzzy` ⇒ trigram similarity ordered by `similarity()` with a threshold.

### 8.4 Media upload flow

1. Client requests `POST /media/presign` (or `/users/me/avatar`) with content-type + size.
2. Server validates type/size, returns a **presigned S3 PUT URL** and the target `s3_key`.
3. Client uploads directly to S3/MinIO.
4. Client confirms by sending the `s3_key`(s) when creating the tweet / saving the avatar; server verifies the object exists.
- Constraints: max 4 images/tweet, max ~5MB each, `image/png|jpeg|webp` only.

### 8.5 Notifications pipeline

- On follow/like/reply, the service persists a `notifications` row and publishes to Redis; heavy fan-out (if any) runs in Celery to keep the request fast.

---

## 9. Frontend details

### 9.1 Stack & structure

- **React 18 + Vite + TypeScript** SPA, **Tailwind CSS** (mobile-first), **TanStack Query** for server state, **Zustand** for client/UI state, **React Router** for routing.
- WebSocket client subscribes on login and updates the notifications store; TanStack Query caches are invalidated/patched on relevant events.

### 9.2 Key screens

- Auth: register, login.
- Home feed (infinite scroll).
- Tweet composer (with LLM "generate" helper) + image attach.
- Tweet detail (tweet + flat replies + reply composer + "summarize thread" LLM action).
- Profile (own/other): avatar, bio, tabs for tweets, followers, following; follow/unfollow.
- User search (exact/prefix/fuzzy toggle).
- Notifications panel with real-time updates and unread badge.
- Profile edit.

### 9.3 UX requirements

- **Responsive, mobile-first:** breakpoints mobile `<640px`, tablet `640–1024px`, desktop `>1024px`.
- **Feedback:** optimistic updates for like/follow with rollback on error; toast notifications for errors/success; skeleton loaders.
- **Animations/transitions:** subtle transitions on likes, new items entering the feed, notification badge, and route changes (respecting `prefers-reduced-motion`).
- **Accessibility:** semantic HTML, keyboard navigation, ARIA labels, sufficient contrast.

### 9.4 Client-side security

- Access token held in memory only; refresh via httpOnly cookie.
- All rendered user content escaped by React (no `dangerouslySetInnerHTML` for user content); links sanitized before rendering.

---

## 10. Cross-cutting concerns

### 10.1 Performance

- Target: ~100 concurrent users, no significant degradation.
- Async I/O throughout; DB connection pooling; keyset pagination; targeted indexes; denormalized counters; short-TTL Redis caching for hot reads; direct-to-S3 media uploads to keep the API off the media path.

### 10.2 Security

- **Passwords:** Argon2id, salted.
- **SQL injection:** parameterized queries via SQLModel/SQLAlchemy only.
- **XSS:** React auto-escaping; input validation; strict CSP header; sanitize/validate links.
- **CSRF:** refresh cookie is `SameSite=Strict` + `Secure` + httpOnly; state-changing requests require the `Bearer` access token (not a cookie), so cross-site form posts can't authenticate.
- **Transport:** HTTPS/WSS enforced in prod; HSTS.
- **Headers:** CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`.
- **Access control:** per-request ownership checks (§7.2).
- **Secrets:** never in code; env/secret files only (§12.5).
- **Uploads:** content-type + size validation; server verifies object existence.

### 10.3 Rate limiting

- Redis-backed, per-user (authenticated) and per-IP (unauthenticated) sliding-window limits, enforced by middleware.
- Suggested defaults (tunable): auth endpoints 10/min/IP; tweet create 30/min/user; likes/follows 60/min/user; AI endpoints 10/min/user + a daily cap; global default 120/min/user.
- `429` responses include `Retry-After` and a standard error body (§6.2).

### 10.4 Logging & monitoring

- **Structured JSON logs** (`structlog`) to stdout with a per-request `request_id`/correlation id (also returned as `X-Request-ID`), user id (when known), method, path, status, latency.
- No PII/secrets in logs (passwords/tokens redacted).
- Health endpoints: `/healthz` (liveness), `/readyz` (DB/Redis readiness).
- **Deferred:** external error tracking (Sentry) and metrics dashboards (Prometheus/Grafana/Loki) — logging format chosen so these drop in later.

---

## 11. AI details

### 11.1 Provider & orchestration

- **Provider-agnostic via the LangChain suite.** The concrete model/provider is selected by configuration (env), so OpenAI, Anthropic, or a local model can be swapped without code changes.
- A thin `ai/` module exposes two use-cases: `generate_tweet(prompt)` and `summarize_thread(tweet_id)`, each backed by a versioned prompt template.

### 11.2 Execution model

- AI calls run in **Celery workers** (not inline), so the API stays responsive. Endpoints return `202` + `job_id`; result delivered via polling or WebSocket event.
- Timeouts and retries (bounded) on provider calls; graceful, user-safe error messages on failure.

### 11.3 Guardrails

- **Output constraints:** generated tweets are truncated/validated to ≤280 chars; summaries capped to a max length.
- **Input constraints:** cap prompt length; strip/deny obvious disallowed content; the thread summarizer only ingests tweets the requester is allowed to read.
- **Content safety:** basic moderation pass (provider moderation endpoint or a simple filter) before returning generated content; refuse/blank on policy violations.
- **Grounding:** thread summaries are built strictly from the referenced tweet + its replies (no external browsing).

### 11.4 Prompt-injection defense

- Treat all user/tweet content as **untrusted data, never instructions**: system prompt is fixed server-side; user content is passed in clearly delimited data fields, never concatenated into the instruction section.
- Instructional preamble tells the model to ignore any instructions contained in the tweet text.
- Output is validated/parsed (length, format) before use; the model is never given tool/authority to perform actions — it only returns text.

### 11.5 Cost & rate limits

- Per-user AI rate limit + daily cap (§10.3).
- Configurable max tokens per request; log token usage per call (without logging content) for cost visibility.
- A global monthly budget guard can disable AI features gracefully when exceeded (config flag).

---

## 12. DevOps details

### 12.1 Environments

- **local/dev:** Docker Compose — API, worker, Postgres, Redis, MinIO, frontend (Vite dev), mailhog optional. Hot reload.
- **test:** ephemeral Compose stack used by CI (Postgres + Redis + MinIO), tests run **inside a container**.
- **prod:** single VPS running Docker Compose — API (Gunicorn/Uvicorn), Celery worker + beat, Postgres, Redis, MinIO (or AWS S3), Nginx reverse proxy + TLS, static frontend build.

### 12.2 Containers

- Separate Dockerfiles for `backend` (multi-stage, slim Python, dependencies installed via **uv**) and `frontend` (build stage → Nginx static stage).
- `docker-compose.yml` (base) + overrides `docker-compose.dev.yml` / `docker-compose.prod.yml`.
- Single `docker compose up` brings up the full local stack.

### 12.3 CI/CD (GitHub Actions)

Pipeline stages:
1. **Lint & type-check:** Ruff + Black (check) + mypy (backend, dependencies installed via `uv sync`); ESLint + `tsc --noEmit` (frontend).
2. **Test:** backend `pytest` with coverage gate ≥ 80%; frontend Vitest coverage ≥ 70%; e2e Playwright against the Compose stack. Tests run **in containers**.
3. **Build:** Docker images for backend + frontend.
4. **Release:** on a semver git tag (`vX.Y.Z`), build and publish tagged images; produce release notes.
5. **Deploy:** (manual/gated) pull images on the VPS and `docker compose up -d`.

### 12.4 Migrations, seeding & deploy automation

- **Alembic** migrations run on deploy (pre-start step).
- **Seed script** (`make seed` / CLI) populates demo users, tweets, follows, likes for dev/test.
- **Makefile** targets: `make up`, `make down`, `make test`, `make lint`, `make seed`, `make migrate`, `make deploy`.
- **Versioning:** semantic versioning via git tags; images tagged with the same version.

### 12.5 Secrets

- Config via environment variables (12-factor). `.env` for local (git-ignored); `.env.example` documents all keys.
- Prod secrets provided via the host's environment / Docker secrets, never committed.
- Secrets include: DB URL, JWT signing key, Redis URL, S3 credentials, LLM provider API key(s).

---

## 13. Testing strategy

Coverage targets: **backend ≥ 80%**, **frontend ≥ 70%**. All test tiers runnable in Docker and in CI.

### 13.1 Backend

- **Unit:** services, validators, auth/token logic, AI guardrail functions (LLM provider mocked).
- **Integration:** API endpoints via `httpx`/`ASGITransport` against a real Postgres + Redis + MinIO in Compose; covers auth flows, feed pagination, likes/follows/replies, search modes, rate limiting, notification persistence.
- **WebSocket tests:** connect, auth rejection, receive a notification within the latency budget.
- **Tools:** `pytest`, `pytest-asyncio`, `coverage`; factory helpers for fixtures; provider calls mocked for AI.

### 13.2 Frontend

- **Unit/component:** Vitest + React Testing Library for components, hooks, stores.
- **Integration:** rendering flows with mocked API (MSW), optimistic update rollback, form validation.

### 13.3 End-to-end

- **Playwright** across the running Compose stack: register → login → post tweet → follow → like → reply → receive real-time notification → search → generate tweet (mocked/limited AI) → summarize thread.
- Responsive checks at the three breakpoints.

### 13.4 Quality gates

- CI fails if coverage thresholds are unmet or lint/type checks fail. AI provider calls are mocked in CI (no real spend).

---

## 14. Project structure

Monorepo:

```
twitter-smart-clone/
├── specification/
│   ├── requirements.md
│   ├── specification.md
│   └── tasks.md               # implementation task tracking
├── docs/                      # living app documentation (architecture, guides, ADRs)
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app factory
│   │   ├── core/                  # config, security, logging, deps, rate limit
│   │   ├── models/                # SQLModel tables
│   │   ├── schemas/               # Pydantic DTOs
│   │   ├── repositories/          # data access
│   │   ├── services/              # business logic + authz
│   │   ├── routers/               # HTTP + WS endpoints
│   │   ├── ws/                    # ConnectionManager + Redis pub/sub
│   │   ├── ai/                    # LangChain chains, prompts, guardrails
│   │   └── workers/               # Celery app + tasks
│   ├── alembic/                   # migrations
│   ├── tests/                     # unit + integration + ws
│   ├── scripts/                   # seed, admin CLIs
│   ├── pyproject.toml
│   ├── uv.lock
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/                   # API client, TanStack Query hooks
│   │   ├── components/
│   │   ├── features/              # feed, tweet, profile, notifications, search, ai
│   │   ├── stores/                # Zustand stores
│   │   ├── routes/
│   │   ├── lib/                   # ws client, utils
│   │   └── main.tsx
│   ├── tests/                     # Vitest + RTL
│   ├── e2e/                       # Playwright
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── Makefile
├── .env.example
├── .github/workflows/            # CI/CD
└── README.md
```

---

## 15. Good practices

Only enforceable/specific practices (verified in CI where possible):

- **Formatting/linting (enforced):** Ruff + Black + mypy (backend); ESLint + Prettier + `tsc --noEmit` (frontend). CI blocks on violations.
- **Typing:** Python type hints on public functions; TypeScript `strict` mode on.
- **Commits & releases:** Conventional Commits; releases via semver git tags (`vX.Y.Z`) that drive image tags (§12).
- **Migrations:** every schema change ships an Alembic migration; no ad-hoc DDL.
- **Config:** 12-factor — all config/secrets via env; `.env.example` kept in sync; no secrets in git (enforced by a secret-scanning step).
- **Error handling:** all API errors use the standard error envelope (§6.2) with a `request_id`.
- **Security defaults:** parameterized queries only; passwords Argon2id; security headers + CSP set globally; rate limits on all mutating and AI endpoints.
- **Testing gates:** coverage thresholds (80%/70%) enforced in CI; AI provider mocked in tests.
- **Separation of concerns:** routers ↔ services ↔ repositories layering respected; no DB access in routers, no HTTP concerns in services.
- **Docs:** README documents local bring-up (`docker compose up`), seeding, testing, and env vars; OpenAPI kept as the API contract source.
```
