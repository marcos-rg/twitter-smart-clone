import { request } from './client'
import type { LikeRelationship } from './types'

const BASE = '/api/v1/tweets'

/** `POST /tweets/{id}/like` — idempotent like. Mirrors `followUser`. */
export function likeTweet(tweetId: string): Promise<LikeRelationship> {
  return request<LikeRelationship>(`${BASE}/${encodeURIComponent(tweetId)}/like`, {
    method: 'POST',
  })
}

/** `DELETE /tweets/{id}/like` — idempotent unlike. Mirrors `unfollowUser`. */
export function unlikeTweet(tweetId: string): Promise<LikeRelationship> {
  return request<LikeRelationship>(`${BASE}/${encodeURIComponent(tweetId)}/like`, {
    method: 'DELETE',
  })
}
