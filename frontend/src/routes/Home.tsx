import { Button, EmptyState } from '../components/ui'
import { useLogout } from '../features/auth/hooks'
import { useAuthStore } from '../stores/auth-store'

/**
 * Placeholder home route. Feature pages (feed, profile, etc.) replace this in
 * later tasks; for now it proves the AppShell + routing + auth guard work end
 * to end. Shows the signed-in user and a logout action (TSC-AUTH-002).
 */
export function Home() {
  const user = useAuthStore((state) => state.user)
  const logout = useLogout()

  return (
    <div>
      <header className="flex items-center justify-between border-b border-border px-4 py-4">
        <div>
          <h1>Twitter Smart Clone</h1>
          {user ? <p className="text-sm text-muted">Signed in as @{user.username}</p> : null}
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
      <div className="p-4">
        <EmptyState
          title="Frontend scaffold ready"
          description="The feed is implemented in a later task. Visit the Design Lab to browse the component library."
        />
      </div>
    </div>
  )
}
