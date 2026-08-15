import { Link } from 'react-router-dom'
import { Avatar, Button } from '../components/ui'
import { LogOutIcon } from '../components/ui/icons'
import { resolveMediaUrl } from '../api/media'
import { useLogout } from '../features/auth/hooks'
import { Feed } from '../features/feed/Feed'
import { useAuthStore } from '../stores/auth-store'

/**
 * Home route: the signed-in user's chronological, infinite-scrolling feed
 * (`Feed`, TSC-FEED-002), behind the same header (signed-in-as link + log
 * out) proven out by the earlier routing/auth-guard scaffold (TSC-AUTH-002).
 */
export function Home() {
  const user = useAuthStore((state) => state.user)
  const logout = useLogout()

  return (
    <div>
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-border bg-canvas/80 px-4 py-3 backdrop-blur-md">
        {user ? (
          <Link
            to={`/profile/${user.username}`}
            className="flex min-w-0 items-center gap-2.5 text-sm text-muted hover:text-foreground"
          >
            <Avatar name={user.name} src={resolveMediaUrl(user.avatar_key)} size="sm" />
            <span className="truncate hover:underline">Signed in as @{user.username}</span>
          </Link>
        ) : (
          <span />
        )}
        <Button
          variant="outline"
          size="sm"
          loading={logout.isPending}
          onClick={() => logout.mutate()}
        >
          <LogOutIcon className="size-4" />
          Log out
        </Button>
      </header>
      <Feed />
    </div>
  )
}
