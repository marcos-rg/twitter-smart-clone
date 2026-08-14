import { Link, useNavigate } from 'react-router-dom'
import { Avatar } from '../ui/Avatar'
import { Skeleton } from '../ui/Skeleton'
import { resolveMediaUrl } from '../../api/media'
import { linkifyContent } from './linkify'
import { TweetImageGallery } from './TweetImageGallery'
import type { TweetView } from '../../api/types'

export interface TweetCardProps {
  tweet: TweetView
}

/**
 * Presentational tweet card. Renders a full `TweetView` (author already
 * embedded — no separate author fetch). Content is always rendered as plain
 * React text nodes, split into segments by the server's `links` spans (see
 * `linkify.ts`) — `dangerouslySetInnerHTML` is never used, so the backend's
 * plain-text contract is preserved end to end.
 *
 * The whole card navigates to `/tweet/{id}` on click; the author name and
 * timestamp are real `<Link>`s (keyboard/screen-reader accessible without
 * relying on the card's own click handler), and every other interactive
 * descendant (content links, the reply action, the like placeholder) calls
 * `stopPropagation` so it doesn't also trigger the card-level navigation.
 *
 * Reposts are out of scope (spec: retweets/quote-tweets excluded) — the
 * repost action from the earlier scaffold has been removed. The like button
 * stays an inert, display-only placeholder (`liked_by_viewer`/`like_count`)
 * — wiring it to `POST/DELETE /tweets/{id}/like` is TSC-LIKE-002.
 */
export function TweetCard({ tweet }: TweetCardProps) {
  const navigate = useNavigate()
  const { author } = tweet
  const segments = linkifyContent(tweet.content, tweet.links)
  const detailPath = `/tweet/${tweet.id}`

  return (
    <article
      aria-label={`Tweet by ${author.name}`}
      onClick={() => navigate(detailPath)}
      className="flex cursor-pointer gap-3 border-b border-border px-4 py-3 transition-colors duration-150 hover:bg-surface-hover/40 motion-reduce:transition-none"
    >
      <Avatar name={author.name} src={resolveMediaUrl(author.avatar_key)} />
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-baseline gap-x-2">
          <Link
            to={`/profile/${author.username}`}
            onClick={(event) => event.stopPropagation()}
            className="font-semibold text-foreground hover:underline"
          >
            {author.name}
          </Link>
          <span className="text-sm text-muted">@{author.username}</span>
          <span aria-hidden="true" className="text-sm text-muted">
            ·
          </span>
          <Link
            to={detailPath}
            onClick={(event) => event.stopPropagation()}
            className="text-sm text-muted hover:underline"
          >
            <time dateTime={tweet.created_at}>{formatTimestamp(tweet.created_at)}</time>
          </Link>
        </header>
        <p className="mt-1 break-words whitespace-pre-wrap text-foreground">
          {segments.map((segment, index) =>
            segment.type === 'link' ? (
              <a
                key={index}
                href={segment.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(event) => event.stopPropagation()}
                className="text-brand hover:underline"
              >
                {segment.text}
              </a>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </p>
        <TweetImageGallery media={tweet.media} />
        <footer className="mt-2 flex max-w-xs justify-between text-sm text-muted">
          <button
            type="button"
            aria-label={`Reply, ${tweet.reply_count} replies`}
            onClick={(event) => {
              event.stopPropagation()
              navigate(detailPath)
            }}
            className="flex cursor-pointer items-center gap-1 rounded-full px-2 py-1 transition-colors duration-150 hover:bg-brand-soft hover:text-brand motion-reduce:transition-none"
          >
            <span aria-hidden="true">💬</span>
            <span aria-hidden="true">{tweet.reply_count}</span>
          </button>
          <button
            type="button"
            aria-label={`${tweet.liked_by_viewer ? 'Liked' : 'Like'}, ${tweet.like_count} likes`}
            onClick={(event) => event.stopPropagation()}
            className={`flex items-center gap-1 rounded-full px-2 py-1 ${
              tweet.liked_by_viewer ? 'text-brand' : ''
            }`}
          >
            <span aria-hidden="true">{tweet.liked_by_viewer ? '❤' : '♡'}</span>
            <span aria-hidden="true">{tweet.like_count}</span>
          </button>
        </footer>
      </div>
    </article>
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
