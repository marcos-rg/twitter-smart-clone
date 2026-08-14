/**
 * Client-side form validation mirroring the backend constraints (spec §7.1;
 * `app/schemas/auth.py`, `app/models/user.py`). Kept in sync deliberately so
 * users get instant feedback instead of waiting on a round trip, while the
 * server remains the source of truth.
 */

const USERNAME_PATTERN = /^[a-zA-Z0-9_]{3,30}$/
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateName(name: string): string | undefined {
  if (!name.trim()) return 'Name is required.'
  if (name.length > 50) return 'Name must be at most 50 characters.'
  return undefined
}

export function validateUsername(username: string): string | undefined {
  if (!username) return 'Username is required.'
  if (!USERNAME_PATTERN.test(username)) {
    return 'Username must be 3-30 characters: letters, numbers, and underscores only.'
  }
  return undefined
}

export function validateEmail(email: string): string | undefined {
  if (!email) return 'Email is required.'
  if (!EMAIL_PATTERN.test(email)) return 'Enter a valid email address.'
  return undefined
}

export function validateRegisterPassword(password: string): string | undefined {
  if (!password) return 'Password is required.'
  if (password.length < 8) return 'Password must be at least 8 characters.'
  if (password.length > 128) return 'Password must be at most 128 characters.'
  return undefined
}

export function validateLoginPassword(password: string): string | undefined {
  if (!password) return 'Password is required.'
  return undefined
}
