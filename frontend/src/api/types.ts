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
  /** Follow-graph fields (TSC-SOC-001). Populated by `GET /users/{username}`;
   * default to `0`/`0`/`false` on any other response shape that happens to
   * validate against this type (e.g. `PATCH /users/me`'s echoed body). */
  followers_count: number
  following_count: number
  /** Whether the authenticated caller follows this profile. Always `false`
   * on one's own profile — self-follow is impossible. */
  is_following: boolean
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

/**
 * `/users/{username}/follow`, `/followers`, `/following` types
 * (spec §6.1, §6.3 "Follows", TSC-SOC-001).
 */

/** `POST`/`DELETE /users/{username}/follow` response: the relationship after
 * the call plus the target's updated follower count, enough to update the UI
 * from this response alone (no profile re-fetch needed). */
export interface FollowRelationship {
  following: boolean
  followers_count: number
}

/** One row of a followers/following list. Deliberately has no
 * `is_following` field — the backend doesn't compute the caller's
 * relationship to each row, so list rows link to a profile rather than
 * rendering a (potentially wrong) follow control of their own. */
export interface FollowUserItem {
  id: string
  name: string
  username: string
  bio: string | null
  avatar_key: string | null
}

export interface FollowListResponse {
  data: FollowUserItem[]
  page: PageInfo
}
