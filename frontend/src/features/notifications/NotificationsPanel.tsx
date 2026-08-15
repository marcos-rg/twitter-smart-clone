import { useMemo, useState } from 'react'
import { Button, EmptyState, ErrorState } from '../../components/ui'
import { useNotificationsStore } from '../../stores/notifications-store'
import { NotificationRow, NotificationRowSkeleton } from './NotificationRow'
import {
  describeNotificationsError,
  useMarkAllNotificationsRead,
  useMarkSelectedNotificationsRead,
  useNotifications,
} from './hooks'

/**
 * Notifications panel (TSC-NOTIF-002): paginated follow/like/reply list,
 * unread badge, and "mark selected"/"mark all" read actions. Live
 * WebSocket events patch the same cache this reads from
 * (`useNotificationsSocket`, mounted once near the app root) — this
 * component itself only reads/mutates via TanStack Query and never touches
 * the socket directly.
 *
 * States covered (acceptance criteria): loading skeletons, a full-page
 * error with retry when the first page fails, a friendly empty state, and
 * cursor-paginated "load more". A `role="status"` banner surfaces
 * reconnecting/offline socket state without blocking the already-loaded
 * list.
 */
export function NotificationsPanel() {
  const query = useNotifications()
  const markAll = useMarkAllNotificationsRead()
  const markSelected = useMarkSelectedNotificationsRead()
  const unreadCount = useNotificationsStore((state) => state.unreadCount)
  const connectionStatus = useNotificationsStore((state) => state.connectionStatus)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const items = useMemo(() => query.data?.pages.flatMap((page) => page.data) ?? [], [query.data])

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function handleMarkSelected() {
    if (selected.size === 0) return
    const ids = Array.from(selected)
    markSelected.mutate(ids, { onSuccess: () => setSelected(new Set()) })
  }

  return (
    <div>
      <header className="border-b border-border px-4 py-4">
        <h1 className="text-xl font-bold text-foreground">Notifications</h1>
      </header>

      {connectionStatus === 'reconnecting' ? (
        <div
          role="status"
          className="border-b border-border bg-surface-hover px-4 py-2 text-center text-sm text-muted"
        >
          Reconnecting…
        </div>
      ) : null}

      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-sm text-muted">
          {unreadCount} unread notification{unreadCount === 1 ? '' : 's'}
        </span>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={selected.size === 0}
            loading={markSelected.isPending}
            onClick={handleMarkSelected}
          >
            Mark selected read
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={unreadCount === 0}
            loading={markAll.isPending}
            onClick={() => markAll.mutate()}
          >
            Mark all read
          </Button>
        </div>
      </div>

      {query.isLoading ? (
        <>
          <NotificationRowSkeleton />
          <NotificationRowSkeleton />
          <NotificationRowSkeleton />
        </>
      ) : query.isError && items.length === 0 ? (
        <div className="p-4">
          <ErrorState
            title="Couldn't load notifications"
            description={describeNotificationsError(query.error)}
            onRetry={() => void query.refetch()}
          />
        </div>
      ) : items.length === 0 ? (
        <div className="p-4">
          <EmptyState
            title="No notifications yet"
            description="Follows, likes, and replies will show up here."
          />
        </div>
      ) : (
        <>
          <ul aria-label="Notifications">
            {items.map((item) => (
              <NotificationRow
                key={item.id}
                item={item}
                selected={selected.has(item.id)}
                onToggleSelected={() => toggleSelected(item.id)}
              />
            ))}
          </ul>

          {query.hasNextPage ? (
            <div className="flex justify-center p-4">
              <Button
                variant="outline"
                loading={query.isFetchingNextPage}
                onClick={() => void query.fetchNextPage()}
              >
                Load more
              </Button>
            </div>
          ) : (
            <p className="p-6 text-center text-sm text-muted">You&apos;re all caught up.</p>
          )}
        </>
      )}
    </div>
  )
}
