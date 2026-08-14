# Authenticated realtime WebSocket infrastructure (`TSC-NOTIF-004`)

The transport that pushes persisted notification events (`TSC-NOTIF-001`) to
online clients: an authenticated `GET /api/v1/ws` endpoint, an in-process
connection registry, a Redis pub/sub bridge for cross-process fan-out, and a
heartbeat reaper for dead sockets (spec §4.2).

This task owns the **transport**. It does not create notifications — that's
`NotificationsService.create_notification` (`TSC-NOTIF-001`) — and no
follow/like/reply trigger calls it yet; those are wired up by `TSC-SOC-*`,
`TSC-LIKE-*`, `TSC-TWEET-*`. Anything published to Redis by any future
trigger is delivered by the infrastructure documented here without further
changes.

## Endpoint

`GET /api/v1/ws?token=<jwt>` — upgraded to a WebSocket.

- **Auth:** the same short-lived JWT access token used for REST (`app.core.security.decode_access_token`),
  passed as the `token` query parameter (spec §4.2: "Auth via short-lived
  access token passed as a query param"). Validated, and the referenced user
  loaded, **before** `websocket.accept()` is ever called.
- **Rejection:** a missing token, an invalid/malformed/expired token, or a
  token for a user that no longer exists closes the handshake with app
  close code `4401` and the connection is never registered — the socket
  never enters `ConnectionManager`, matching the task's acceptance
  criterion verbatim. Starlette denies the WebSocket upgrade at the HTTP
  level when `close()` is called before `accept()`, so a rejected client
  never gets a live socket to begin with.
- **Multi-tab:** a user may hold more than one connection at a time (e.g.
  two browser tabs); each is tracked independently and each receives its
  own copy of every event addressed to that user.

## Architecture

```
backend/app/ws/
├── manager.py        # ConnectionManager: in-process registry keyed by user_id
├── redis_bridge.py   # NotificationRedisBridge: PSUBSCRIBE notifications:* -> manager
├── heartbeat.py       # HeartbeatReaper: ping live connections, reap idle ones
└── runtime.py         # WebSocketRuntime: composes + lifecycle-manages the three above

backend/app/routers/ws.py   # GET /api/v1/ws: auth-on-connect, register, receive loop
```

`app.main.create_app` wraps `app.core.resources.create_lifespan` (DB/Redis/S3
handles) with a second lifespan layer that builds a `WebSocketRuntime` from
`app.state.resources` and starts/stops it around the same `yield`, storing it
on `app.state.ws_runtime`. Kept as a separate composition (`app/ws/runtime.py`
+ `app/main.py`'s `_create_lifespan`) rather than folded into
`app.core.resources` so that module stays scoped to the async resource
handles it already documents itself as owning.

### `ConnectionManager` (`app/ws/manager.py`)

An in-process `dict[user_id, dict[connection_id, Connection]]`. One instance
lives on `app.state.ws_runtime.manager` per process/worker.

- `register(user_id, websocket)` / `unregister(user_id, connection_id)` —
  called only from the router, only for an already-`accept()`ed socket.
- `send_to_user(user_id, message)` — fans a raw text message out to every
  connection currently registered for that user. A failed send on one
  connection (dead socket) is logged and that one connection is
  deregistered; it never blocks delivery to the user's other connections.
- `all_connections()` — a snapshot used by the heartbeat reaper's sweep.

### `NotificationRedisBridge` (`app/ws/redis_bridge.py`)

Rather than `SUBSCRIBE`/`UNSUBSCRIBE`-ing a per-recipient Redis channel each
time a socket connects/disconnects, one process opens a single long-lived
`PSUBSCRIBE notifications:*` for its entire lifetime (spec's documented
alternative to per-user `SUBSCRIBE`: "a single `notifications` channel with
user routing"). Every message's channel name (`notifications:{recipient_id}`,
from `app.services.notification_publisher`) is parsed back into a
`recipient_id` and handed to `ConnectionManager.send_to_user`.

Consequences of this design:

- Exactly one Redis connection per process for this purpose, regardless of
  how many users/connections it currently holds.
- A reconnect (unregister + re-register in `ConnectionManager`) only touches
  local, in-process state — the Redis-side subscription is untouched, so
  **nothing about a reconnect can leak a Redis subscription**; there isn't a
  per-connection one to leak in the first place.
- Any process can `PUBLISH` and every process routes the message locally —
  this is what makes "an event published by one API process reaches a
  socket held by another process" work, with no sticky sessions and no
  pub/sub fan-out logic tied to which worker happens to hold a given socket.

**Startup is lazy**, matching every other resource in `app.core.resources`
("Connections are lazy ... so the app can still start even if a dependency
is temporarily down"). `WebSocketRuntime.start()` launches the bridge's
background task without blocking on `PSUBSCRIBE` succeeding; the task itself
retries with a 1s backoff until Redis is reachable, then keeps retrying if
the subscription later drops (Redis restart, network blip). Folding the
initial subscribe into a blocking `start()` call was tried first and it
broke app boot entirely (and therefore `/readyz`) whenever Redis was
unavailable at process start — reverted in favor of this retry loop after
`tests/test_health.py::test_readyz_fails_when_every_dependency_is_unavailable`
caught the regression.

### `HeartbeatReaper` (`app/ws/heartbeat.py`)

Every `ws_heartbeat_interval_seconds` (default `20.0`), the reaper sweeps
every registered connection:

- If idle (no inbound activity — any client message, including a `pong`)
  for longer than `ws_heartbeat_timeout_seconds` (default `45.0`): closes
  the socket with app close code `4408` and deregisters it.
- Otherwise: sends an application-level `{"type": "ping"}` text frame.

**Reconnect contract:** the server holds no per-connection session to
resume. A reconnect is a brand-new authenticated handshake with a brand-new
connection id; missed events are not replayed over the socket. The client
reconciles via `GET /notifications` after reconnecting — the database, not
the socket, is the source of truth (spec §4.2: "If the recipient has no
active socket, the persisted notification is delivered on next
fetch/next connect"). One heartbeat interval of slack is built into the
default timeout being longer than one interval, so a single slow tick
doesn't reap a healthy connection.

### Router (`app/routers/ws.py`)

```
validate token (query param) --reject--> close(4401), never registered
        |
        v
load user from DB --not found--> close(4401), never registered
        |
        v
accept() -> register() -> receive loop (any message refreshes liveness)
        |
        v (WebSocketDisconnect / any other error)
finally: unregister()
```

## Message envelope

Identical to the Redis event envelope documented in
[`notifications-backend.md`](./notifications-backend.md)
(`app.schemas.notifications.NotificationEvent`) — the bridge forwards the
`PUBLISH`ed JSON payload verbatim, with no reshaping:

```json
{
  "type": "notification",
  "event": "follow | like | reply",
  "data": {
    "notification_id": "...",
    "recipient_id": "...",
    "actor": { "id": "...", "username": "...", "name": "...", "avatar_key": "..." },
    "tweet_id": "...",
    "is_read": false,
    "created_at": "..."
  }
}
```

Plus one transport-level frame the client must recognize and ignore (or
reply to) that is **not** a notification event:

```json
{"type": "ping"}
```

A client is expected to reply with `{"type": "pong"}` (any inbound text
message counts as liveness — the router does not currently parse message
content beyond "something arrived").

## Configuration (`app.core.config.Settings`)

| Setting | Default | Purpose |
|---|---|---|
| `ws_heartbeat_interval_seconds` | `20.0` | How often the reaper sweeps / pings. |
| `ws_heartbeat_timeout_seconds` | `45.0` | Idle threshold before a connection is reaped. |

Both are constructor overrides on `Settings`, used by the test suite to run
the heartbeat sweep on a much shorter cycle without changing production
defaults.

## Verification commands

- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend uv run pytest tests/test_ws.py -q`
  — auth rejection (missing/invalid/expired token, never entering the
  registry), multi-tab fan-out (each connection receives a real,
  service-created notification exactly once), reconnect leaves no leftover
  registry entry, an event published from one `FastAPI` app instance
  reaches a socket held by a second independent instance (both pointed at
  the same real Postgres/Redis — the multi-process criterion), delivery
  latency under the 2s budget, and idle-connection reaping within the
  configured heartbeat timeout.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"`
  — full suite (152 tests) passes, 97% statement coverage (gate: 90%).
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app tests scripts`
  all pass against every file this task added or modified (pre-existing
  formatting drift in `app/repositories/tweet_media.py`, unrelated to this
  task, is untouched).

### A note on test flakiness this task ran into (and fixed)

Two timing assumptions in the WebSocket test harness (`starlette.testclient`)
turned out not to hold under full-suite/coverage load, both fixed in
`tests/test_ws.py` rather than papered over:

1. **Reconnect teardown races the client-side close.** `WebSocketTestSession.__exit__`
   enqueues a disconnect message *and then, in the same teardown, cancels the
   underlying task* — occasionally winning that race before the app task
   resumes and runs its `finally: manager.unregister(...)`. The test now
   calls `ws.close()` explicitly and polls for deregistration *inside* the
   `with` block, before that implicit teardown-cancel can race it.
2. **A sub-100ms heartbeat interval isn't reliable under coverage
   instrumentation.** With `ws_heartbeat_interval_seconds=0.05`, the
   reaper's very first sweep could already exceed a `0.12s` timeout outright
   (no ping ever sent) if the event loop was busy — a real, correct reap,
   just not the sequence the test originally assumed. The test now uses more
   headroom (`0.1s` / `0.4s`) and accepts zero-or-more pings before the
   eventual reap, rather than requiring exactly one.
