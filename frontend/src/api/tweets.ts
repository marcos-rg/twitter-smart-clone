import { request } from './client'
import type { CursorPageParams } from './users'
import type { TweetCreateRequest, TweetListResponse, TweetView } from './types'

const BASE = '/api/v1/tweets'

/** `POST /tweets` — creates a root tweet (`parent_tweet_id` omitted) or a
 * flat reply (`parent_tweet_id` set). The backend re-validates content
 * whitespace/length and media ownership; see `docs/tweet-backend.md`. */
export function createTweet(payload: TweetCreateRequest): Promise<TweetView> {
  return request<TweetView>(BASE, { method: 'POST', body: payload })
}

/** `GET /tweets/{id}` — a single tweet. 404s (`ApiError.status === 404`) for
 * an unknown or malformed id. */
export function getTweet(id: string): Promise<TweetView> {
  return request<TweetView>(`${BASE}/${encodeURIComponent(id)}`)
}

/** `GET /tweets/{id}/replies` — flat replies, oldest first, cursor-paginated.
 * Replying to a reply is impossible (backend-enforced), so a reply's own
 * replies list is always empty rather than an error. */
export function listReplies(id: string, params: CursorPageParams = {}): Promise<TweetListResponse> {
  const query = new URLSearchParams()
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  return request<TweetListResponse>(
    `${BASE}/${encodeURIComponent(id)}/replies${qs ? `?${qs}` : ''}`,
  )
}
