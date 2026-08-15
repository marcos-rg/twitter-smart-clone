import { useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Logomark, useToast } from '../components/ui'
import { LoginForm } from '../features/auth/LoginForm'
import { useAuthStore } from '../stores/auth-store'

interface LocationState {
  from?: { pathname: string }
  prefillEmail?: string
}

/** Login screen. Shows a one-time "session expired" toast when arriving here
 * because a refresh failed (spec §7.1 acceptance: "failed refresh clears auth
 * state and redirects to login"), and returns the user to wherever they were
 * headed before the redirect. */
export function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { toast } = useToast()
  const sessionExpired = useAuthStore((state) => state.sessionExpired)
  const acknowledgeExpired = useAuthStore((state) => state.acknowledgeExpired)
  const state = location.state as LocationState | null

  useEffect(() => {
    if (sessionExpired) {
      toast('Your session has expired. Please log in again.', 'error')
      acknowledgeExpired()
    }
    // Runs once per mount of this page — acknowledging clears the flag so a
    // later back/forward navigation does not re-show the toast.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleSuccess() {
    const destination = state?.from?.pathname ?? '/'
    navigate(destination, { replace: true })
  }

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4 py-10 sm:min-h-screen">
      <div className="w-full max-w-sm rounded-card border border-border bg-surface/60 p-8 shadow-card">
        <header className="flex flex-col items-center gap-3 text-center">
          <Logomark className="size-11" />
          <div>
            <h1>Log in</h1>
            <p className="mt-1 text-sm text-muted">Welcome back.</p>
          </div>
        </header>
        <div className="mt-6">
          <LoginForm onSuccess={handleSuccess} initialEmail={state?.prefillEmail ?? ''} />
        </div>
        <p className="mt-6 text-center text-sm text-muted">
          Don&apos;t have an account? <Link to="/register">Sign up</Link>
        </p>
      </div>
    </div>
  )
}
