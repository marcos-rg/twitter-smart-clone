import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  notificationsQueryKey,
  useNotificationsSocket,
} from '../../../src/features/notifications/hooks'
import { useAuthStore } from '../../../src/stores/auth-store'
import { useNotificationsStore } from '../../../src/stores/notifications-store'
import type { WebSocketLike } from '../../../src/features/notifications/ws-client'

/**
 * Lifecycle tests for the app-root socket bridge (`useNotificationsSocket`,
 * mounted once via `NotificationsSocketBridge` in `App.tsx`): connects only
 * while authenticated, never leaks a connection across unmount/logout, and
 * clears user-specific notification state on logout (TSC-NOTIF-002
 * acceptance criteria). The socket's own reconnect/backoff/heartbeat
 * mechanics are unit-tested in isolation in `ws-client.test.ts`; this file
 * covers the React-level wiring around it, so the global `WebSocket` is
 * stubbed with the same fake used there.
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
  closeCalls = 0

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(): void {}

  close(): void {
    this.closeCalls += 1
    this.readyState = 3
  }

  triggerOpen(): void {
    this.readyState = 1
    this.onopen?.()
  }
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

function signIn(accessToken = 'token-abc') {
  act(() => {
    useAuthStore.setState({
      accessToken,
      user: {
        id: 'user-1',
        name: 'Ada Lovelace',
        username: 'ada',
        email: 'ada@example.com',
        bio: null,
        avatar_key: null,
        created_at: '2026-01-01T00:00:00Z',
      },
      status: 'authenticated',
      sessionExpired: false,
    })
  })
}

describe('useNotificationsSocket', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: 'idle',
      sessionExpired: false,
    })
    useNotificationsStore.getState().reset()
  })

  it('does not connect while unauthenticated', () => {
    const queryClient = makeClient()
    renderHook(() => useNotificationsSocket(), { wrapper: wrapper(queryClient) })

    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('connects once the session becomes authenticated, using the access token', async () => {
    const queryClient = makeClient()
    renderHook(() => useNotificationsSocket(), { wrapper: wrapper(queryClient) })

    signIn('my-access-token')

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(FakeWebSocket.instances[0].url).toContain('token=my-access-token')
  })

  it('unmounting disconnects the socket (no leaked connection)', async () => {
    const queryClient = makeClient()
    const { unmount } = renderHook(() => useNotificationsSocket(), {
      wrapper: wrapper(queryClient),
    })
    signIn()
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const ws = FakeWebSocket.instances[0]
    ws.triggerOpen()

    unmount()

    expect(ws.closeCalls).toBe(1)
  })

  it('logout closes the socket and clears user-specific notification state', async () => {
    const queryClient = makeClient()
    queryClient.setQueryData(notificationsQueryKey(), {
      pages: [{ data: [{ id: 'n1' }], page: { next_cursor: null }, unread_count: 3 }],
      pageParams: [undefined],
    })
    useNotificationsStore.getState().setUnreadCount(3)

    renderHook(() => useNotificationsSocket(), { wrapper: wrapper(queryClient) })
    signIn()
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const ws = FakeWebSocket.instances[0]
    ws.triggerOpen()

    act(() => {
      useAuthStore.setState({
        accessToken: null,
        user: null,
        status: 'unauthenticated',
        sessionExpired: false,
      })
    })

    await waitFor(() => expect(ws.closeCalls).toBe(1))
    expect(useNotificationsStore.getState().unreadCount).toBe(0)
    expect(queryClient.getQueryData(notificationsQueryKey())).toBeUndefined()
  })
})
