import { Avatar } from '../ui/Avatar'
import { Skeleton } from '../ui/Skeleton'

export interface TweetCardProps {
  authorName: string
  authorHandle: string
  authorAvatarUrl?: string
  /** ISO timestamp, rendered as a relative-friendly label. */
  timestamp: string
  content: string
  replyCount?: number
  repostCount?: number
  likeCount?: number
}

/**
 * Presentational tweet card shell. Action buttons are inert placeholders —
 * wiring them to the API is part of the tweet/like feature tasks. Long
 * content wraps instead of overflowing (`break-words`).
 */
export function TweetCard({
  authorName,
  authorHandle,
  authorAvatarUrl,
  timestamp,
  content,
  replyCount = 0,
  repostCount = 0,
  likeCount = 0,
}: TweetCardProps) {
  return (
    <article
      aria-label={`Tweet by ${authorName}`}
      className="flex gap-3 border-b border-border px-4 py-3 transition-colors duration-150 hover:bg-surface-hover/40 motion-reduce:transition-none"
    >
      <Avatar name={authorName} src={authorAvatarUrl} />
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-semibold text-foreground">{authorName}</span>
          <span className="text-sm text-muted">@{authorHandle}</span>
          <span aria-hidden="true" className="text-sm text-muted">
            ·
          </span>
          <time dateTime={timestamp} className="text-sm text-muted">
            {formatTimestamp(timestamp)}
          </time>
        </header>
        <p className="mt-1 break-words whitespace-pre-wrap text-foreground">{content}</p>
        <footer className="mt-2 flex max-w-xs justify-between text-sm text-muted">
          <ActionButton label={`Reply, ${replyCount} replies`} count={replyCount} icon="💬" />
          <ActionButton label={`Repost, ${repostCount} reposts`} count={repostCount} icon="🔁" />
          <ActionButton label={`Like, ${likeCount} likes`} count={likeCount} icon="♡" />
        </footer>
      </div>
    </article>
  )
}

function ActionButton({ label, count, icon }: { label: string; count: number; icon: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      className="flex cursor-pointer items-center gap-1 rounded-full px-2 py-1 transition-colors duration-150 hover:bg-brand-soft hover:text-brand motion-reduce:transition-none"
    >
      <span aria-hidden="true">{icon}</span>
      <span aria-hidden="true">{count}</span>
    </button>
  )
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

/** Loading placeholder with the same layout as a loaded TweetCard. */
export function TweetCardSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading tweet"
      className="flex gap-3 border-b border-border px-4 py-3"
    >
      <Skeleton className="size-10 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-32" />
      </div>
    </div>
  )
}
