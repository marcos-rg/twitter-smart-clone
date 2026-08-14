import { NavLink, useParams } from 'react-router-dom'
import { Button, EmptyState, ErrorState } from '../../components/ui'
import { UserCard, UserCardSkeleton } from '../users/UserCard'
import { describeUsersError } from '../users/hooks'
import { useFollowers, useFollowing } from './hooks'

export type FollowListKind = 'followers' | 'following'

const copy: Record<FollowListKind, { title: string; empty: (username: string) => string }> = {
  followers: {
    title: 'Followers',
    empty: (username) => `@${username} doesn't have any followers yet.`,
  },
  following: {
    title: 'Following',
    empty: (username) => `@${username} isn't following anyone yet.`,
  },
}

/**
 * Paginated followers/following list for a profile (TSC-SOC-002). Shared by
 * the `/profile/:username/followers` and `/profile/:username/following`
 * routes, which double as the tab switcher (`NavLink`s below) — navigating
 * between them preserves each list's own TanStack Query cache, so returning
 * to a list you already paged through doesn't refetch from scratch or lose
 * your place.
 *
 * List rows link to the user's profile but do not render their own
 * follow/unfollow control: the backend's `/followers` and `/following`
 * responses report each row's identity only, not whether the signed-in
 * caller follows that row, so a per-row button here would have to guess.
 */
export function FollowList({ kind }: { kind: FollowListKind }) {
  const { username } = useParams<{ username: string }>()
  const followers = useFollowers(kind === 'followers' ? username : undefined)
  const following = useFollowing(kind === 'following' ? username : undefined)
  const query = kind === 'followers' ? followers : following

  const items = query.data?.pages.flatMap((page) => page.data) ?? []
  const { title, empty } = copy[kind]

  if (!username) return null

  return (
    <div>
      <header className="px-4 py-4">
        <h1 className="text-xl font-bold text-foreground">{title}</h1>
        <p className="text-sm text-muted">@{username}</p>
      </header>

      <nav aria-label="Follow lists" className="flex border-b border-border">
        <NavLink
          to={`/profile/${username}/followers`}
          className={({ isActive }) =>
            [
              'flex-1 px-4 py-2 text-center text-sm font-semibold transition-colors duration-150 motion-reduce:transition-none',
              isActive
                ? 'border-b-2 border-brand text-foreground'
                : 'text-muted hover:bg-surface-hover hover:text-foreground',
            ].join(' ')
          }
        >
          Followers
        </NavLink>
        <NavLink
          to={`/profile/${username}/following`}
          className={({ isActive }) =>
            [
              'flex-1 px-4 py-2 text-center text-sm font-semibold transition-colors duration-150 motion-reduce:transition-none',
              isActive
                ? 'border-b-2 border-brand text-foreground'
                : 'text-muted hover:bg-surface-hover hover:text-foreground',
            ].join(' ')
          }
        >
          Following
        </NavLink>
      </nav>

      <div>
        {query.isLoading ? (
          <>
            <UserCardSkeleton />
            <UserCardSkeleton />
            <UserCardSkeleton />
          </>
        ) : query.isError ? (
          <div className="p-4">
            <ErrorState
              title={`Couldn't load ${title.toLowerCase()}`}
              description={describeUsersError(query.error)}
              onRetry={() => void query.refetch()}
            />
          </div>
        ) : items.length === 0 ? (
          <div className="p-4">
            <EmptyState title={`No ${title.toLowerCase()}`} description={empty(username)} />
          </div>
        ) : (
          <>
            {items.map((item) => (
              <UserCard key={item.id} name={item.name} username={item.username} bio={item.bio} />
            ))}
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
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
