import { useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useToast } from '../components/ui'
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
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-10">
      <header>
        <h1>Log in</h1>
        <p className="mt-1 text-sm text-muted">Welcome back.</p>
      </header>
      <LoginForm onSuccess={handleSuccess} initialEmail={state?.prefillEmail ?? ''} />
      <p className="text-sm text-muted">
        Don&apos;t have an account? <Link to="/register">Sign up</Link>
      </p>
    </div>
  )
}
