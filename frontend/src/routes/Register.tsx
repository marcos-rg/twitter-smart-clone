import { useNavigate } from 'react-router-dom'
import { Link } from 'react-router-dom'
import { Logomark, useToast } from '../components/ui'
import { RegisterForm } from '../features/auth/RegisterForm'

/** Registration screen. On success, routes to login with the email
 * pre-filled — `/auth/register` issues no tokens, so the user still has to
 * authenticate explicitly (spec §7.1: register and login are separate). */
export function Register() {
  const navigate = useNavigate()
  const { toast } = useToast()

  function handleSuccess(email: string) {
    toast('Account created. Log in to continue.', 'success')
    navigate('/login', { replace: true, state: { prefillEmail: email } })
  }

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4 py-10 sm:min-h-screen">
      <div className="w-full max-w-sm rounded-card border border-border bg-surface/60 p-8 shadow-card">
        <header className="flex flex-col items-center gap-3 text-center">
          <Logomark className="size-11" />
          <div>
            <h1>Create your account</h1>
            <p className="mt-1 text-sm text-muted">Join the conversation.</p>
          </div>
        </header>
        <div className="mt-6">
          <RegisterForm onSuccess={handleSuccess} />
        </div>
        <p className="mt-6 text-center text-sm text-muted">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  )
}
