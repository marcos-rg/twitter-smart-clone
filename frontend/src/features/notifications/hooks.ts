import { useEffect } from 'react'
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from '@tanstack/react-query'
import * as notificationsApi from '../../api/notifications'
import { ApiError } from '../../api/client'
import { useAuthStore } from '../../stores/auth-store'
import { useNotificationsStore } from '../../stores/notifications-store'
import { NotificationsSocket } from './ws-client'
import type { NotificationEvent, NotificationItem, NotificationListResponse } from '../../api/types'

export function describeNotificationsError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Check your connection and try again.'
}

export function notificationsQueryKey() {
  return ['notifications'] as const
}

const NOTIFICATIONS_PAGE_SIZE = 20

/** Paginated notifications list (TSC-NOTIF-002), newest first. Also keeps
 * `useNotificationsStore`'s badge count in sync with the server-authoritative
 * `unread_count` every time a fresh first page lands — initial load, a
 * manual refetch, or the reconcile-after-reconnect refetch triggered by
 * `useNotificationsSocket`. */
export function useNotifications() {
  const query = useInfiniteQuery({
    queryKey: notificationsQueryKey(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      notificationsApi.listNotifications({ cursor: pageParam, limit: NOTIFICATIONS_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
  })

  const firstPageUnreadCount = query.data?.pages[0]?.unread_count
  useEffect(() => {
    if (firstPageUnreadCount !== undefined) {
      useNotificationsStore.getState().setUnreadCount(firstPageUnreadCount)
    }
  }, [firstPageUnreadCount])

  return query
}

function findCachedNotification(
  queryClient: QueryClient,
  id: string,
): NotificationItem | undefined {
  const cache =
    queryClient.getQueryData<InfiniteData<NotificationListResponse>>(notificationsQueryKey())
  for (const page of cache?.pages ?? []) {
    const found = page.data.find((item) => item.id === id)
    if (found) return found
  }
  return undefined
}

/** Applies a live WebSocket `NotificationEvent` to the cached list: prepends
 * it to the first cached page and bumps the unread badge — but only when
 * `notification_id` isn't already present anywhere in the cache, so a
 * follow/like/reply event that arrives live and is later also returned by a
 * REST fetch (e.g. the reconcile-after-reconnect refetch) renders exactly
 * once (acceptance criterion). A no-op if the list has never been fetched —
 * nothing cached to prepend into; the next `GET /notifications` picks it up
 * naturally since it's already durably persisted server-side. */
export function applyNotificationEvent(queryClient: QueryClient, event: NotificationEvent): void {
  const { data } = event
  if (findCachedNotification(queryClient, data.notification_id)) return

  const item: NotificationItem = {
    id: data.notification_id,
    type: event.event,
    actor: data.actor,
    tweet_id: data.tweet_id,
    is_read: data.is_read,
    created_at: data.created_at,
  }

  const patched = queryClient.setQueryData<InfiniteData<NotificationListResponse> | undefined>(
    notificationsQueryKey(),
    (current) => {
      if (!current || current.pages.length === 0) return current
      const [firstPage, ...rest] = current.pages
      return {
        ...current,
        pages: [{ ...firstPage, data: [item, ...firstPage.data] }, ...rest],
      }
    },
  )
  // Only bump the badge if there was a cache to patch into and the item
  // wasn't already there (checked above) — otherwise the badge would drift
  // from the server-authoritative count a later fetch will restore anyway.
  if (patched) useNotificationsStore.getState().increment()
}

function patchNotificationsRead(queryClient: QueryClient, ids: Set<string> | 'all'): void {
  queryClient.setQueryData<InfiniteData<NotificationListResponse> | undefined>(
    notificationsQueryKey(),
    (current) => {
      if (!current) return current
      return {
        ...current,
        pages: current.pages.map((page) => ({
          ...page,
          data: page.data.map((item) =>
            item.is_read || (ids !== 'all' && !ids.has(item.id))
              ? item
              : { ...item, is_read: true },
          ),
        })),
      }
    },
  )
}

/** Marks every currently-unread notification as read. */
export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => notificationsApi.markNotificationsRead({}),
    onSuccess: (result) => {
      patchNotificationsRead(queryClient, 'all')
      useNotificationsStore.getState().setUnreadCount(result.unread_count)
    },
  })
}

/** Marks a specific set of notification ids as read (row click or bulk
 * "mark selected" action share this one mutation). */
export function useMarkSelectedNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) =>
      notificationsApi.markNotificationsRead({ notification_ids: ids }),
    onSuccess: (result, ids) => {
      patchNotificationsRead(queryClient, new Set(ids))
      useNotificationsStore.getState().setUnreadCount(result.unread_count)
    },
  })
}

/**
 * Owns the authenticated WebSocket connection's lifecycle, mounted once near
 * the app root (`NotificationsSocketBridge`).
 *
 * - Connects only while `useAuthStore`'s status is `'authenticated'`; the
 *   token itself is read fresh on every (re)connect attempt via
 *   `useAuthStore.getState()` rather than captured in the effect's
 *   dependency array, so a background token refresh never needs to tear
 *   down and rebuild the socket.
 * - A reconnect (after having been open before) invalidates the cached list
 *   so it refetches and reconciles against the DB — the server replays
 *   nothing over the socket itself (spec: "the persisted notification is
 *   delivered on next fetch/next connect").
 * - Logout (status leaves `'authenticated'`) disconnects the socket and
 *   clears user-specific notification state — the unread badge resets and
 *   the cached list is dropped so the next signed-in user never sees a
 *   flash of the previous user's notifications (acceptance criterion).
 * - The effect's cleanup always disconnects the socket it created, so
 *   navigating away/unmounting never leaks a connection or its reconnect
 *   timer (acceptance criterion).
 * - Also primes the unread badge with one cheap `GET /notifications?limit=1`
 *   call as soon as a session is authenticated, so the nav badge is correct
 *   even before the notifications panel has ever been opened (it's not read
 *   from the socket — only future events arrive there — nor written into
 *   the `['notifications']` list cache, so it can't race or conflict with
 *   `useNotifications`' own fetch/pagination of that same cache).
 */
export function useNotificationsSocket(): void {
  const status = useAuthStore((state) => state.status)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (status !== 'authenticated') {
      useNotificationsStore.getState().reset()
      queryClient.removeQueries({ queryKey: notificationsQueryKey() })
      return
    }

    let cancelled = false
    void notificationsApi
      .listNotifications({ limit: 1 })
      .then((page) => {
        if (!cancelled) useNotificationsStore.getState().setUnreadCount(page.unread_count)
      })
      .catch(() => {
        // Best-effort priming only — the panel's own fetch (or a live
        // event) will populate the badge if this one fails.
      })

    const socket = new NotificationsSocket({
      getToken: () => useAuthStore.getState().accessToken,
      buildUrl: (token) => notificationsApi.websocketUrl(token),
      onEvent: (event) => applyNotificationEvent(queryClient, event),
      onStatusChange: (nextStatus) =>
        useNotificationsStore.getState().setConnectionStatus(nextStatus),
      onReconnected: () => {
        void queryClient.invalidateQueries({ queryKey: notificationsQueryKey() })
      },
    })
    socket.connect()

    return () => {
      cancelled = true
      socket.disconnect()
    }
  }, [status, queryClient])
}
