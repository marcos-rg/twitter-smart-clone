import { Link } from 'react-router-dom'
import { Button } from '../components/ui'
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
      <header className="flex items-center justify-between border-b border-border px-4 py-4">
        <div>
          <h1>Twitter Smart Clone</h1>
          {user ? (
            <Link
              to={`/profile/${user.username}`}
              className="text-sm text-muted hover:text-foreground hover:underline"
            >
              Signed in as @{user.username}
            </Link>
          ) : null}
        </div>
        <Button
          variant="outline"
          size="sm"
          loading={logout.isPending}
          onClick={() => logout.mutate()}
        >
          Log out
        </Button>
      </header>
      <Feed />
    </div>
  )
}
