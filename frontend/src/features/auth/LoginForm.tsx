import { useState, type FormEvent } from 'react'
import { Button, Input, useToast } from '../../components/ui'
import { useLogin, describeAuthError } from './hooks'
import { validateEmail, validateLoginPassword } from './validation'

export interface LoginFormProps {
  onSuccess: () => void
  initialEmail?: string
}

/** Email + password login form: inline validation, submit loading state, and
 * a toast on failure (spec §9.3 feedback, §9.4 client-side security). */
export function LoginForm({ onSuccess, initialEmail = '' }: LoginFormProps) {
  const [email, setEmail] = useState(initialEmail)
  const [password, setPassword] = useState('')
  const [touched, setTouched] = useState(false)
  const login = useLogin()
  const { toast } = useToast()

  const emailError = touched ? validateEmail(email) : undefined
  const passwordError = touched ? validateLoginPassword(password) : undefined

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    if (validateEmail(email) || validateLoginPassword(password)) return

    login.mutate(
      { email, password },
      {
        onSuccess: () => onSuccess(),
        onError: (error) => toast(describeAuthError(error), 'error'),
      },
    )
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={emailError}
        required
      />
      <Input
        label="Password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={passwordError}
        required
      />
      <Button type="submit" loading={login.isPending} className="mt-2">
        Log in
      </Button>
    </form>
  )
}
