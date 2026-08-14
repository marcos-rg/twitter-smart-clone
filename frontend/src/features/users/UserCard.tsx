import { Link } from 'react-router-dom'
import { Avatar, Skeleton } from '../../components/ui'

export interface UserCardProps {
  name: string
  username: string
  bio: string | null
}

/** Compact user row for search results (and future followers/following
 * lists). The whole row links to the profile. */
export function UserCard({ name, username, bio }: UserCardProps) {
  return (
    <Link
      to={`/profile/${username}`}
      className="flex gap-3 border-b border-border px-4 py-3 transition-colors duration-150 hover:bg-surface-hover/40 motion-reduce:transition-none"
    >
      <Avatar name={name} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-foreground">{name}</p>
        <p className="truncate text-sm text-muted">@{username}</p>
        {bio ? (
          <p className="mt-1 line-clamp-2 break-words text-sm text-foreground">{bio}</p>
        ) : null}
      </div>
    </Link>
  )
}

/** Loading placeholder with the same layout as a loaded UserCard. */
export function UserCardSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading user"
      className="flex gap-3 border-b border-border px-4 py-3"
    >
      <Skeleton className="size-10 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>
  )
}
