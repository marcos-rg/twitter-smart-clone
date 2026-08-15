import type { NotificationEvent } from '../../api/types'

export type SocketStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

/** Minimal shape this module depends on — matches the browser `WebSocket`
 * constructor/instance, but narrow enough that tests can pass a fake
 * implementation without stubbing every unused member. */
export interface WebSocketLike {
  readyState: number
  send(data: string): void
  close(code?: number): void
  onopen: (() => void) | null
  onmessage: ((event: { data: string }) => void) | null
  onclose: (() => void) | null
  onerror: (() => void) | null
}

export interface WebSocketLikeConstructor {
  new (url: string): WebSocketLike
  readonly OPEN: number
}

export interface NotificationsSocketOptions {
  /** Read fresh on every (re)connect attempt — access tokens are
   * short-lived and rotate via refresh, so a token captured once at
   * construction time could go stale across a reconnect. Returning `null`
   * (no session) skips connecting. */
  getToken: () => string | null
  /** Builds the full `ws(s)://…/ws?token=…` URL for a given token. */
  buildUrl: (token: string) => string
  onEvent: (event: NotificationEvent) => void
  onStatusChange?: (status: SocketStatus) => void
  /** Fired when a connection that was previously open is re-established.
   * Missed events are never replayed over the socket (server contract), so
   * the caller should reconcile via `GET /notifications` here. */
  onReconnected?: () => void
  /** Injectable `WebSocket` constructor for tests; defaults to the global. */
  WebSocketImpl?: WebSocketLikeConstructor
  minBackoffMs?: number
  maxBackoffMs?: number
}

const DEFAULT_MIN_BACKOFF_MS = 1000
const DEFAULT_MAX_BACKOFF_MS = 30000

/**
 * Authenticated WebSocket client for `GET /api/v1/ws` (TSC-NOTIF-002,
 * transport documented in `docs/websocket-realtime.md`).
 *
 * - **Reconnect:** any non-explicit close schedules a reconnect after a
 *   bounded exponential backoff (`minBackoffMs * 2^attempt`, capped at
 *   `maxBackoffMs`), reset to the first step as soon as a connection opens
 *   successfully.
 * - **Heartbeat:** the server pings with `{"type":"ping"}`; this client
 *   replies `{"type":"pong"}` on any inbound ping — matching
 *   `docs/websocket-realtime.md`'s documented contract — which also keeps
 *   the connection's liveness fresh server-side.
 * - **Reconnect-restores-state contract:** the server holds no
 *   per-connection session to resume, so `onReconnected` is the hook for
 *   the caller to refetch `GET /notifications` and reconcile the cache —
 *   this client never assumes missed events were replayed.
 * - **No leaked sockets/timers:** `disconnect()` clears any pending
 *   reconnect timer, detaches every socket handler, and closes the socket;
 *   after it returns, nothing scheduled by this instance can still fire.
 */
export class NotificationsSocket {
  private readonly getToken: () => string | null
  private readonly buildUrl: (token: string) => string
  private readonly onEvent: (event: NotificationEvent) => void
  private readonly onStatusChange?: (status: SocketStatus) => void
  private readonly onReconnected?: () => void
  private readonly WebSocketImpl: WebSocketLikeConstructor
  private readonly minBackoffMs: number
  private readonly maxBackoffMs: number

  private socket: WebSocketLike | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private attempt = 0
  private everConnected = false
  private explicitlyClosed = true
  private status: SocketStatus = 'idle'

  constructor(options: NotificationsSocketOptions) {
    this.getToken = options.getToken
    this.buildUrl = options.buildUrl
    this.onEvent = options.onEvent
    this.onStatusChange = options.onStatusChange
    this.onReconnected = options.onReconnected
    this.WebSocketImpl = options.WebSocketImpl ?? (WebSocket as unknown as WebSocketLikeConstructor)
    this.minBackoffMs = options.minBackoffMs ?? DEFAULT_MIN_BACKOFF_MS
    this.maxBackoffMs = options.maxBackoffMs ?? DEFAULT_MAX_BACKOFF_MS
  }

  connect(): void {
    this.explicitlyClosed = false
    this.clearReconnectTimer()
    this.open()
  }

  getStatus(): SocketStatus {
    return this.status
  }

  /** Explicit disconnect (logout, unmount, no session). Idempotent. */
  disconnect(): void {
    this.explicitlyClosed = true
    this.attempt = 0
    this.everConnected = false
    this.clearReconnectTimer()
    if (this.socket) {
      const socket = this.socket
      socket.onopen = null
      socket.onmessage = null
      socket.onclose = null
      socket.onerror = null
      socket.close()
      this.socket = null
    }
    this.setStatus('closed')
  }

  private open(): void {
    const token = this.getToken()
    if (!token) {
      this.setStatus('closed')
      return
    }

    this.setStatus(this.attempt > 0 ? 'reconnecting' : 'connecting')
    const socket = new this.WebSocketImpl(this.buildUrl(token))
    this.socket = socket

    socket.onopen = () => {
      const wasReconnect = this.everConnected
      this.everConnected = true
      this.attempt = 0
      this.setStatus('open')
      if (wasReconnect) this.onReconnected?.()
    }
    socket.onmessage = (event) => this.handleMessage(event.data)
    socket.onclose = () => {
      this.socket = null
      if (this.explicitlyClosed) {
        this.setStatus('closed')
        return
      }
      this.scheduleReconnect()
    }
    socket.onerror = () => {
      // The transport always follows an error with a close event, which
      // drives the actual reconnect scheduling above — nothing to do here.
    }
  }

  private handleMessage(raw: string): void {
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      return
    }
    if (!parsed || typeof parsed !== 'object') return
    const type = (parsed as { type?: unknown }).type
    if (type === 'ping') {
      this.send({ type: 'pong' })
      return
    }
    if (type === 'notification') {
      this.onEvent(parsed as NotificationEvent)
    }
  }

  private send(message: unknown): void {
    if (this.socket && this.socket.readyState === this.WebSocketImpl.OPEN) {
      this.socket.send(JSON.stringify(message))
    }
  }

  private scheduleReconnect(): void {
    this.setStatus('reconnecting')
    const delay = Math.min(this.maxBackoffMs, this.minBackoffMs * 2 ** this.attempt)
    this.attempt += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, delay)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private setStatus(status: SocketStatus): void {
    this.status = status
    this.onStatusChange?.(status)
  }
}
