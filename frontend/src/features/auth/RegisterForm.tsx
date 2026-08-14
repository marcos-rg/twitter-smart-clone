import { useState, type FormEvent } from 'react'
import { Button, Input, useToast } from '../../components/ui'
import { useRegister, describeAuthError } from './hooks'
import {
  validateEmail,
  validateName,
  validateRegisterPassword,
  validateUsername,
} from './validation'

export interface RegisterFormProps {
  onSuccess: (email: string) => void
}

interface FieldErrors {
  name?: string
  username?: string
  email?: string
  password?: string
}

/** Registration form: name, username, email, password with inline validation
 * mirroring the backend constraints (spec §7.1). Registration does not log
 * the user in (the API returns no tokens for `/auth/register`) — on success
 * the caller routes to login with the email pre-filled. */
export function RegisterForm({ onSuccess }: RegisterFormProps) {
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [touched, setTouched] = useState(false)
  const register = useRegister()
  const { toast } = useToast()

  const errors: FieldErrors = touched
    ? {
        name: validateName(name),
        username: validateUsername(username),
        email: validateEmail(email),
        password: validateRegisterPassword(password),
      }
    : {}

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    if (
      validateName(name) ||
      validateUsername(username) ||
      validateEmail(email) ||
      validateRegisterPassword(password)
    ) {
      return
    }

    register.mutate(
      { name, username, email, password },
      {
        onSuccess: () => onSuccess(email),
        onError: (error) => toast(describeAuthError(error), 'error'),
      },
    )
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input
        label="Name"
        autoComplete="name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={errors.name}
        required
      />
      <Input
        label="Username"
        autoComplete="username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        error={errors.username}
        hint="3-30 characters: letters, numbers, and underscores."
        required
      />
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={errors.email}
        required
      />
      <Input
        label="Password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={errors.password}
        hint={errors.password ? undefined : 'At least 8 characters.'}
        required
      />
      <Button type="submit" loading={register.isPending} className="mt-2">
        Create account
      </Button>
    </form>
  )
}
