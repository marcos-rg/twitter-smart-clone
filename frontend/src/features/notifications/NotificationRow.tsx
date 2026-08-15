import { useNavigate } from 'react-router-dom'
import { Avatar } from '../../components/ui/Avatar'
import { Skeleton } from '../../components/ui/Skeleton'
import { resolveMediaUrl } from '../../api/media'
import { useMarkSelectedNotificationsRead } from './hooks'
import type { NotificationItem } from '../../api/types'

function verbFor(item: NotificationItem): string {
  switch (item.type) {
    case 'follow':
      return 'followed you'
    case 'like':
      return 'liked your tweet'
    case 'reply':
      return 'replied to your tweet'
  }
}

function destinationFor(item: NotificationItem): string {
  if (item.type !== 'follow' && item.tweet_id) return `/tweet/${item.tweet_id}`
  return `/profile/${item.actor.username}`
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export interface NotificationRowProps {
  item: NotificationItem
  selected: boolean
  onToggleSelected: () => void
}

/**
 * One notification row (TSC-NOTIF-002): a checkbox for bulk "mark selected
 * as read", and a keyboard-operable button covering the rest of the row
 * that navigates to the relevant profile/tweet and — if the notification is
 * still unread — marks it read on the way there (mirrors how opening a
 * notification behaves in mainstream clients). Unread rows get a tinted
 * background and a small dot so the state is legible without relying on
 * color alone (the surrounding text/weight also differs).
 */
export function NotificationRow({ item, selected, onToggleSelected }: NotificationRowProps) {
  const navigate = useNavigate()
  const markRead = useMarkSelectedNotificationsRead()

  function handleOpen() {
    if (!item.is_read) markRead.mutate([item.id])
    navigate(destinationFor(item))
  }

  return (
    <li
      className={`flex items-start gap-3 border-b border-border px-4 py-3 ${
        item.is_read ? '' : 'bg-brand-soft/40'
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggleSelected}
        aria-label={`Select notification: ${item.actor.name} ${verbFor(item)}`}
        className="mt-1.5 size-4 shrink-0 accent-brand"
      />
      <button
        type="button"
        onClick={handleOpen}
        className="flex min-w-0 flex-1 items-start gap-3 text-left transition-colors duration-150 motion-reduce:transition-none"
      >
        <Avatar name={item.actor.name} src={resolveMediaUrl(item.actor.avatar_key)} size="sm" />
        <div className="min-w-0 flex-1">
          <p className={`text-sm text-foreground ${item.is_read ? '' : 'font-semibold'}`}>
            {item.actor.name} {verbFor(item)}
          </p>
          <time dateTime={item.created_at} className="text-xs text-muted">
            {formatTimestamp(item.created_at)}
          </time>
        </div>
        {!item.is_read ? (
          <span aria-label="Unread" className="mt-1.5 size-2 shrink-0 rounded-full bg-brand" />
        ) : null}
      </button>
    </li>
  )
}

/** Loading placeholder with the same layout as a loaded row. */
export function NotificationRowSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading notification"
      className="flex items-start gap-3 border-b border-border px-4 py-3"
    >
      <Skeleton className="mt-1.5 size-4" />
      <Skeleton className="size-10 shrink-0 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-24" />
      </div>
    </div>
  )
}
