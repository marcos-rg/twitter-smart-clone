import { useNavigate } from 'react-router-dom'
import { Link } from 'react-router-dom'
import { useToast } from '../components/ui'
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
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-10">
      <header>
        <h1>Create your account</h1>
        <p className="mt-1 text-sm text-muted">Join the conversation.</p>
      </header>
      <RegisterForm onSuccess={handleSuccess} />
      <p className="text-sm text-muted">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </div>
  )
}
