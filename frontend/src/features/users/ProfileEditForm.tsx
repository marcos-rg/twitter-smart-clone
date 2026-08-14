import { useState, type FormEvent } from 'react'
import { Button, Input, Textarea, useToast } from '../../components/ui'
import { ApiError } from '../../api/client'
import { describeUsersError, useUpdateProfile } from './hooks'
import { validateBio, validateEmail, validateName, validateUsername } from './validation'

export interface ProfileEditFormValues {
  name: string
  username: string
  email: string
  bio: string
}

export interface ProfileEditFormProps {
  initialValues: ProfileEditFormValues
  onSuccess: (username: string) => void
  onCancel: () => void
}

interface FieldErrors {
  name?: string
  username?: string
  email?: string
  bio?: string
}

/**
 * Edit form for the signed-in user's own profile. Fields are seeded once from
 * `initialValues` via `useState`'s lazy initializer — they are never
 * re-derived from a background refetch of the profile, so if the submit
 * fails (e.g. a 409 username/email conflict) the user's in-progress edits are
 * preserved exactly as typed rather than being clobbered back to the old
 * server values (TSC-USER-002 acceptance criterion).
 */
export function ProfileEditForm({ initialValues, onSuccess, onCancel }: ProfileEditFormProps) {
  const [name, setName] = useState(initialValues.name)
  const [username, setUsername] = useState(initialValues.username)
  const [email, setEmail] = useState(initialValues.email)
  const [bio, setBio] = useState(initialValues.bio)
  const [touched, setTouched] = useState(false)
  const updateProfile = useUpdateProfile()
  const { toast } = useToast()

  const errors: FieldErrors = touched
    ? {
        name: validateName(name),
        username: validateUsername(username),
        email: validateEmail(email),
        bio: validateBio(bio),
      }
    : {}

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    if (
      validateName(name) ||
      validateUsername(username) ||
      validateEmail(email) ||
      validateBio(bio)
    ) {
      return
    }

    updateProfile.mutate(
      { name, username, email, bio },
      {
        onSuccess: (user) => onSuccess(user.username),
        onError: (error) => {
          // 409 conflicts (username/email already taken) surface the
          // server's specific message; anything else falls back to a
          // generic one. Either way, the fields above keep the user's input.
          if (error instanceof ApiError && error.status === 409) {
            toast(error.message, 'error')
            return
          }
          toast(describeUsersError(error), 'error')
        },
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
      <Textarea
        label="Bio"
        value={bio}
        onChange={(event) => setBio(event.target.value)}
        error={errors.bio}
        hint={errors.bio ? undefined : `${bio.length}/160`}
      />
      <div className="mt-2 flex gap-2">
        <Button type="submit" loading={updateProfile.isPending}>
          Save
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={updateProfile.isPending}
        >
          Cancel
        </Button>
      </div>
    </form>
  )
}
