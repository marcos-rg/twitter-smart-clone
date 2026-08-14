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

/**
 * `/tweets/*` and `/users/{username}/tweets` types (spec §6.3 "Tweets &
 * feed", TSC-TWEET-001/002). `TweetView` is the single shape all four
 * tweet-reading endpoints (`POST /tweets`, `GET /tweets/{id}`,
 * `GET /tweets/{id}/replies`, `GET /users/{username}/tweets`) render — see
 * `backend/app/schemas/tweets.py`.
 */

export interface TweetAuthor {
  id: string
  username: string
  name: string
  avatar_key: string | null
}

export interface TweetMediaOut {
  key: string
  content_type: string
  position: number
}

/** One `(url, start, end)` safe-link span over `TweetView.content` — see
 * `backend/app/services/link_extraction.py`. `start`/`end` are Unicode
 * code-point offsets into `content`; only `http`/`https` URLs are ever
 * present. The frontend must never render `content` as HTML — only overlay
 * real `<a>` elements at these server-validated spans. */
export interface LinkEntity {
  url: string
  start: number
  end: number
}

export interface TweetView {
  id: string
  author: TweetAuthor
  content: string
  parent_tweet_id: string | null
  like_count: number
  reply_count: number
  /** Whether the authenticated caller has liked this tweet. Wired to
   * `POST`/`DELETE /tweets/{id}/like` by `LikeButton` (TSC-LIKE-002). */
  liked_by_viewer: boolean
  media: TweetMediaOut[]
  links: LinkEntity[]
  created_at: string
}

/** Body of `POST /tweets`. `parent_tweet_id` present ⇒ a flat reply (the
 * backend rejects replying to a reply with 422); omitted/`null` ⇒ a root
 * tweet. */
export interface TweetCreateRequest {
  content: string
  parent_tweet_id?: string | null
  media_keys?: string[]
}

export interface TweetListResponse {
  data: TweetView[]
  page: PageInfo
}

/**
 * `/tweets/{id}/like` types (spec §6.1, §6.3 "Likes", TSC-LIKE-001/002).
 */

/** `POST`/`DELETE /tweets/{id}/like` response: the relationship after the
 * call plus the tweet's updated like count, enough to update the UI from
 * this response alone (no tweet re-fetch needed). Mirrors
 * `FollowRelationship`. */
export interface LikeRelationship {
  liked: boolean
  like_count: number
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

/**
 * `/media/*` presign/confirm and `/users/me/avatar` types (spec §6.3, §8.4,
 * TSC-MEDIA-001/002).
 */

export type MediaPurpose = 'avatar' | 'tweet_image'

export interface PresignFileRequest {
  content_type: string
  size_bytes: number
}

export interface PresignedUpload {
  key: string
  upload_url: string
  content_type: string
  expires_at: string
}

export interface ConfirmedMedia {
  key: string
  content_type: string
  size_bytes: number
}
