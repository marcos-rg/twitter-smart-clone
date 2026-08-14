/**
 * Client-side validation for profile editing, mirroring the backend
 * constraints (`app/models/user.py`, `app/schemas/users.py`). Name, username,
 * and email rules are identical to registration, so they're reused directly
 * from `features/auth/validation` rather than duplicated and risking drift.
 */
export { validateEmail, validateName, validateUsername } from '../auth/validation'

const BIO_MAX_LENGTH = 160

export function validateBio(bio: string): string | undefined {
  if (bio.length > BIO_MAX_LENGTH) {
    return `Bio must be at most ${BIO_MAX_LENGTH} characters.`
  }
  return undefined
}

export { BIO_MAX_LENGTH }
