import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  applyNotificationEvent,
  notificationsQueryKey,
  resetLiveNotificationDedupe,
  useMarkAllNotificationsRead,
  useMarkSelectedNotificationsRead,
} from '../../../src/features/notifications/hooks'
import { useNotificationsStore } from '../../../src/stores/notifications-store'
import { server } from '../../mocks/server'
import type {
  NotificationEvent,
  NotificationItem,
  NotificationListResponse,
} from '../../../src/api/types'

/**
 * Cache/store-level tests for the notifications feature (TSC-NOTIF-002).
 * Exercised directly against a `QueryClient` + `useNotificationsStore` (no
 * rendered UI, no live socket) so the de-duplication and mark-read fan-out
 * can be asserted precisely — the socket's own reconnect/backoff/heartbeat
 * behavior is covered in `ws-client.test.ts`.
 */

function makeItem(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 'notif-1',
    type: 'like',
    actor: { id: 'user-2', username: 'grace', name: 'Grace Hopper', avatar_key: null },
    tweet_id: 'tweet-1',
    is_read: false,
    created_at: '2026-08-14T00:00:00Z',
    ...overrides,
  }
}

function makeEvent(
  id: string,
  overrides: Partial<NotificationEvent['data']> = {},
): NotificationEvent {
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
      ...overrides,
    },
  }
}

function seedList(queryClient: QueryClient, items: NotificationItem[], unreadCount: number) {
  const page: NotificationListResponse = {
    data: items,
    page: { next_cursor: null },
    unread_count: unreadCount,
  }
  queryClient.setQueryData(notificationsQueryKey(), { pages: [page], pageParams: [undefined] })
}

function readItems(queryClient: QueryClient): NotificationItem[] {
  const cache = queryClient.getQueryData(notificationsQueryKey()) as
    { pages: NotificationListResponse[] } | undefined
  return cache?.pages.flatMap((page) => page.data) ?? []
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

describe('applyNotificationEvent', () => {
  beforeEach(() => {
    useNotificationsStore.getState().reset()
    resetLiveNotificationDedupe()
  })

  it('prepends a live event to the cached first page and bumps the unread badge', () => {
    const queryClient = makeClient()
    seedList(queryClient, [makeItem({ id: 'notif-old' })], 1)

    applyNotificationEvent(queryClient, makeEvent('notif-new'))

    const items = readItems(queryClient)
    expect(items.map((item) => item.id)).toEqual(['notif-new', 'notif-old'])
    expect(useNotificationsStore.getState().unreadCount).toBe(1)
  })

  it('renders a follow/like/reply event exactly once even when it is already present from REST (de-duplication by notification_id)', () => {
    const queryClient = makeClient()
    seedList(queryClient, [makeItem({ id: 'notif-1' })], 1)

    applyNotificationEvent(queryClient, makeEvent('notif-1'))

    const items = readItems(queryClient)
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('notif-1')
    // Already-present events don't double-bump the badge.
    expect(useNotificationsStore.getState().unreadCount).toBe(0)
  })

  it('still bumps the unread badge when the list has never been fetched (e.g. the panel was never opened), even though there is nothing to prepend into', () => {
    // Regression test: the badge used to only bump when `setQueryData`
    // actually patched an existing list cache, so a signed-in user who
    // never opened the notifications panel never saw the badge move at all
    // — reported after this task's first pass shipped.
    const queryClient = makeClient()

    expect(() => applyNotificationEvent(queryClient, makeEvent('notif-1'))).not.toThrow()

    expect(queryClient.getQueryData(notificationsQueryKey())).toBeUndefined()
    expect(useNotificationsStore.getState().unreadCount).toBe(1)
  })

  it('does not double-bump the badge for a duplicate live redelivery even without a list cache', () => {
    // De-duplicated via the session-scoped `seenLiveNotificationIds` set
    // (not just the query cache), since a redelivered event after a
    // reconnect could otherwise double-count the badge before the panel
    // has ever been opened.
    const queryClient = makeClient()

    applyNotificationEvent(queryClient, makeEvent('notif-1'))
    applyNotificationEvent(queryClient, makeEvent('notif-1'))

    expect(useNotificationsStore.getState().unreadCount).toBe(1)
  })
})

describe('useMarkAllNotificationsRead / useMarkSelectedNotificationsRead', () => {
  afterEach(() => {
    server.resetHandlers()
    useNotificationsStore.getState().reset()
  })

  it('marks every item read and syncs the unread store from the server response', async () => {
    server.use(
      http.post('*/api/v1/notifications/read', () =>
        HttpResponse.json({ marked_read: 2, unread_count: 0 }),
      ),
    )
    const queryClient = makeClient()
    seedList(
      queryClient,
      [makeItem({ id: 'a', is_read: false }), makeItem({ id: 'b', is_read: false })],
      2,
    )
    useNotificationsStore.getState().setUnreadCount(2)

    const { result } = renderHook(() => useMarkAllNotificationsRead(), {
      wrapper: wrapper(queryClient),
    })
    act(() => result.current.mutate())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(readItems(queryClient).every((item) => item.is_read)).toBe(true)
    expect(useNotificationsStore.getState().unreadCount).toBe(0)
  })

  it('marks only the selected ids read, leaving the rest untouched', async () => {
    server.use(
      http.post('*/api/v1/notifications/read', () =>
        HttpResponse.json({ marked_read: 1, unread_count: 1 }),
      ),
    )
    const queryClient = makeClient()
    seedList(
      queryClient,
      [makeItem({ id: 'a', is_read: false }), makeItem({ id: 'b', is_read: false })],
      2,
    )

    const { result } = renderHook(() => useMarkSelectedNotificationsRead(), {
      wrapper: wrapper(queryClient),
    })
    act(() => result.current.mutate(['a']))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const items = readItems(queryClient)
    expect(items.find((item) => item.id === 'a')?.is_read).toBe(true)
    expect(items.find((item) => item.id === 'b')?.is_read).toBe(false)
    expect(useNotificationsStore.getState().unreadCount).toBe(1)
  })

  it('marking an already-read notification again is idempotent (no double-flip, cache stays read)', async () => {
    server.use(
      http.post('*/api/v1/notifications/read', () =>
        HttpResponse.json({ marked_read: 0, unread_count: 0 }),
      ),
    )
    const queryClient = makeClient()
    seedList(queryClient, [makeItem({ id: 'a', is_read: true })], 0)

    const { result } = renderHook(() => useMarkSelectedNotificationsRead(), {
      wrapper: wrapper(queryClient),
    })
    act(() => result.current.mutate(['a']))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(readItems(queryClient)[0].is_read).toBe(true)
  })
})
