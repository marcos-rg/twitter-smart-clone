import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  NotificationsSocket,
  type SocketStatus,
  type WebSocketLike,
  type WebSocketLikeConstructor,
} from '../../../src/features/notifications/ws-client'
import type { NotificationEvent } from '../../../src/api/types'

/**
 * Unit tests for the WebSocket client (TSC-NOTIF-002 acceptance criteria:
 * bounded exponential backoff on disconnect, reconnect never leaks a socket
 * or timer, ping/pong heartbeat). Exercised against a fake `WebSocket`
 * implementation with test-controlled `open()`/`close()`/`message()`
 * triggers and fake timers, rather than a real socket — deterministic and
 * fast, and it's this class's own reconnect/backoff/cleanup logic under
 * test, not a real network stack.
 */
class FakeWebSocket implements WebSocketLike {
  static readonly OPEN = 1
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  closeCalls = 0

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.closeCalls += 1
    this.readyState = 3
  }

  triggerOpen(): void {
    this.readyState = 1
    this.onopen?.()
  }

  triggerMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  /** Simulates the transport closing the connection (server drop, network
   * blip) — distinct from `close()`, which is what `disconnect()` calls. */
  triggerServerClose(): void {
    this.readyState = 3
    this.onclose?.()
  }
}

const FakeWebSocketCtor = FakeWebSocket as unknown as WebSocketLikeConstructor

function makeEvent(id: string): NotificationEvent {
  return {
    type: 'notification',
    event: 'like',
    data: {
      notification_id: id,
      recipient_id: 'user-1',
      actor: { id: 'user-2', username: 'grace', name: 'Grace Hopper', avatar_key: null },
      tweet_id: 'tweet-1',
      is_read: false,
      created_at: '2026-08-14T00:00:00Z',
    },
  }
}

describe('NotificationsSocket', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function makeSocket(overrides: { getToken?: () => string | null } = {}) {
    const onEvent = vi.fn()
    const statuses: SocketStatus[] = []
    const onReconnected = vi.fn()
    const socket = new NotificationsSocket({
      getToken: overrides.getToken ?? (() => 'token-abc'),
      buildUrl: (token) => `wss://example.test/api/v1/ws?token=${token}`,
      onEvent,
      onStatusChange: (status) => statuses.push(status),
      onReconnected,
      WebSocketImpl: FakeWebSocketCtor,
      minBackoffMs: 100,
      maxBackoffMs: 400,
    })
    return { socket, onEvent, onReconnected, statuses }
  }

  it('connects to buildUrl(token) using the token from getToken()', () => {
    const { socket } = makeSocket({ getToken: () => 'my-token' })
    socket.connect()

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toBe('wss://example.test/api/v1/ws?token=my-token')
  })

  it('does not open a socket when there is no token, and reports closed', () => {
    const { socket, statuses } = makeSocket({ getToken: () => null })
    socket.connect()

    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(statuses).toEqual(['closed'])
  })

  it('replies with {"type":"pong"} on an inbound heartbeat ping', () => {
    const { socket } = makeSocket()
    socket.connect()
    const ws = FakeWebSocket.instances[0]
    ws.triggerOpen()

    ws.triggerMessage({ type: 'ping' })

    expect(ws.sent).toEqual([JSON.stringify({ type: 'pong' })])
  })

  it('forwards notification events to onEvent and ignores malformed/unknown frames', () => {
    const { socket, onEvent } = makeSocket()
    socket.connect()
    const ws = FakeWebSocket.instances[0]
    ws.triggerOpen()

    ws.triggerMessage('not json{{{')
    ws.triggerMessage({ type: 'something-else' })
    expect(onEvent).not.toHaveBeenCalled()

    const event = makeEvent('notif-1')
    ws.triggerMessage(event)
    expect(onEvent).toHaveBeenCalledWith(event)
  })

  it('schedules a reconnect with bounded exponential backoff after an unexpected close', () => {
    const { socket, statuses } = makeSocket()
    socket.connect()
    FakeWebSocket.instances[0].triggerOpen()
    expect(statuses).toEqual(['connecting', 'open'])

    // First drop: reconnect after minBackoffMs (100ms).
    FakeWebSocket.instances[0].triggerServerClose()
    expect(statuses.at(-1)).toBe('reconnecting')
    vi.advanceTimersByTime(99)
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeWebSocket.instances).toHaveLength(2)

    // Second drop without ever reopening: backoff doubles (200ms), not a
    // fresh minBackoffMs.
    FakeWebSocket.instances[1].triggerServerClose()
    vi.advanceTimersByTime(199)
    expect(FakeWebSocket.instances).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(FakeWebSocket.instances).toHaveLength(3)

    // Third drop: would be 400ms (doubling again) but capped at
    // maxBackoffMs (400ms) either way.
    FakeWebSocket.instances[2].triggerServerClose()
    vi.advanceTimersByTime(399)
    expect(FakeWebSocket.instances).toHaveLength(3)
    vi.advanceTimersByTime(1)
    expect(FakeWebSocket.instances).toHaveLength(4)

    // Fourth drop: still capped at maxBackoffMs (400ms), never grows
    // unbounded.
    FakeWebSocket.instances[3].triggerServerClose()
    vi.advanceTimersByTime(400)
    expect(FakeWebSocket.instances).toHaveLength(5)
  })

  it('resets the backoff attempt counter once a connection reopens successfully', () => {
    const { socket } = makeSocket()
    socket.connect()
    FakeWebSocket.instances[0].triggerOpen()

    FakeWebSocket.instances[0].triggerServerClose()
    vi.advanceTimersByTime(100) // back to open at attempt 0's delay
    expect(FakeWebSocket.instances).toHaveLength(2)
    FakeWebSocket.instances[1].triggerOpen() // reopened -> attempt resets to 0

    FakeWebSocket.instances[1].triggerServerClose()
    // If the attempt counter had NOT reset, this would need 200ms; since it
    // reset on reopen, 100ms (the first-attempt delay) is enough again.
    vi.advanceTimersByTime(100)
    expect(FakeWebSocket.instances).toHaveLength(3)
  })

  it('calls onReconnected only when a connection that was previously open re-opens, not on the first connect', () => {
    const { socket, onReconnected } = makeSocket()
    socket.connect()
    FakeWebSocket.instances[0].triggerOpen()
    expect(onReconnected).not.toHaveBeenCalled()

    FakeWebSocket.instances[0].triggerServerClose()
    vi.advanceTimersByTime(100)
    FakeWebSocket.instances[1].triggerOpen()
    expect(onReconnected).toHaveBeenCalledTimes(1)
  })

  it('disconnect() closes a live socket and detaches its handlers', () => {
    const { socket, statuses } = makeSocket()
    socket.connect()
    const ws = FakeWebSocket.instances[0]
    ws.triggerOpen()

    socket.disconnect()

    expect(ws.closeCalls).toBe(1)
    expect(ws.onopen).toBeNull()
    expect(ws.onmessage).toBeNull()
    expect(ws.onclose).toBeNull()
    expect(statuses.at(-1)).toBe('closed')
  })

  it('disconnect() cancels a pending reconnect timer so nothing reconnects afterward', () => {
    const { socket } = makeSocket()
    socket.connect()
    const ws = FakeWebSocket.instances[0]
    ws.triggerOpen()
    ws.triggerServerClose() // schedules a reconnect in 100ms

    socket.disconnect()

    vi.advanceTimersByTime(10_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('disconnect() before any connect() is a safe no-op', () => {
    const { socket } = makeSocket()
    expect(() => socket.disconnect()).not.toThrow()
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('a fresh connect() after disconnect() reconnects cleanly (e.g. re-login)', () => {
    const { socket } = makeSocket()
    socket.connect()
    FakeWebSocket.instances[0].triggerOpen()
    socket.disconnect()

    socket.connect()
    expect(FakeWebSocket.instances).toHaveLength(2)
  })
})
