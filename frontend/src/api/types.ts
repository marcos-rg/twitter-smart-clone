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

/**
 * `/users/*` profile, timeline, and search types (spec §6.2, §7.2).
 *
 * `UserPublicProfile` deliberately has no `email` field — the backend's
 * `GET /users/{username}` never returns one, for self or anyone else, so the
 * type system itself makes it impossible for a public-profile view to render
 * an email address.
 */
export interface UserPublicProfile {
  id: string
  name: string
  username: string
  bio: string | null
  avatar_key: string | null
  created_at: string
}

/** `PATCH /users/me` response: the public profile shape plus the owner's own
 * email. Identical to `UserPublic` (the auth endpoints already return this
 * shape for the signed-in user), aliased here for domain clarity. */
export type UserPrivateProfile = UserPublic

export type SearchMode = 'exact' | 'prefix' | 'fuzzy'

/** All fields optional — the backend requires at least one to be set, which
 * the caller (a full edit form that always sends every field) satisfies
 * trivially. */
export interface UserProfileUpdateRequest {
  name?: string
  username?: string
  email?: string
  bio?: string
}

export interface PageInfo {
  next_cursor: string | null
}

export interface UserSearchItem {
  id: string
  name: string
  username: string
  bio: string | null
  avatar_key: string | null
}

export interface UserSearchResponse {
  data: UserSearchItem[]
  page: PageInfo
}

export interface UserTimelineItem {
  id: string
  author_id: string
  content: string
  parent_tweet_id: string | null
  like_count: number
  reply_count: number
  created_at: string
}

export interface UserTimelineResponse {
  data: UserTimelineItem[]
  page: PageInfo
}
