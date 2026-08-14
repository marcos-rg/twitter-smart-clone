"""`GET /api/v1/ws` — the realtime notification stream (spec §4.2).

**Auth:** a short-lived access token passed as the `token` query parameter,
validated on connect (spec: "Auth via short-lived access token passed as a
query param ... validated on connect. Unauthenticated upgrades are
rejected."). Validation happens *before* `websocket.accept()`: an
invalid/expired/missing token or a token for a deleted user closes the
handshake without ever calling `ConnectionManager.register`, satisfying
"invalid/expired WebSocket credentials are rejected without entering the
registry."

**Lifecycle:** accept → register → receive-loop (any inbound message,
including a heartbeat `pong`, refreshes the connection's liveness) →
`WebSocketDisconnect`/error → always deregister in `finally`, so a reconnect
(new socket, new connection id) never leaves the old entry behind.

**Reconnect contract:** the server holds no per-connection server-side
session to resume — a reconnect is simply a brand-new authenticated
handshake that gets a brand-new connection id. Missed events while
disconnected are not replayed over the socket; the client is expected to
reconcile via `GET /notifications` after reconnecting (spec §4.2: "If the
recipient has no active socket, the persisted notification is delivered on
next fetch/next connect" — the DB, not the socket, is the source of truth).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.core.resources import AppResources
from app.core.security import InvalidTokenError, decode_access_token
from app.repositories.users import UserRepository
from app.ws.runtime import WebSocketRuntime

router = APIRouter(tags=["websocket"])

logger = structlog.get_logger("app.ws.router")

#: App-defined WebSocket close code for a rejected handshake (missing,
#: malformed, expired, or otherwise invalid credentials). In the 4000-4999
#: private-use range reserved by RFC 6455 for application codes.
WS_CLOSE_UNAUTHENTICATED = 4401


@router.websocket("/api/v1/ws")
async def notifications_ws(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    resources: AppResources = websocket.app.state.resources
    runtime: WebSocketRuntime = websocket.app.state.ws_runtime

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=WS_CLOSE_UNAUTHENTICATED)
        return

    try:
        user_id = decode_access_token(token, settings)
    except InvalidTokenError:
        await websocket.close(code=WS_CLOSE_UNAUTHENTICATED)
        return

    async with resources.db_sessionmaker() as session:
        user = await UserRepository(session).get(user_id)
    if user is None:
        await websocket.close(code=WS_CLOSE_UNAUTHENTICATED)
        return

    # Only past this point does the connection ever touch the registry —
    # everything above can reject without `accept()`/`register()` running.
    await websocket.accept()
    connection = runtime.manager.register(user.id, websocket)
    await logger.ainfo("ws_connected", user_id=str(user.id), connection_id=connection.id)
    try:
        while True:
            await websocket.receive_text()
            runtime.manager.touch(user.id, connection.id)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - any other socket failure still deregisters cleanly
        await logger.awarning(
            "ws_connection_error",
            user_id=str(user.id),
            connection_id=connection.id,
            exc_info=True,
        )
    finally:
        runtime.manager.unregister(user.id, connection.id)
        await logger.ainfo("ws_disconnected", user_id=str(user.id), connection_id=connection.id)
