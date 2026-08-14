/**
 * Shared HTTP + auth API types (spec §6.2, §6.3, §7.1).
 */

/** The public user shape returned by `/auth/register`, `/auth/me`, and login. */
export interface UserPublic {
  id: string
  name: string
  username: string
  email: string
  bio: string | null
  avatar_key: string | null
  created_at: string
}

/** `POST /auth/login` and `POST /auth/refresh` response body. */
export interface AccessTokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user?: UserPublic | null
}

export interface RegisterPayload {
  name: string
  username: string
  email: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

/** A single field-level validation issue (spec §6.2 error `details[]`). */
export interface ApiErrorDetail {
  field?: string
  issue: string
}

/** Uniform error body shape (spec §6.2, RFC-9457-inspired). */
export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: ApiErrorDetail[]
    request_id?: string
  }
}
