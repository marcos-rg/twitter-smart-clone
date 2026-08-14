import { request } from './client'
import type { CursorPageParams } from './users'
import type { FollowListResponse, FollowRelationship } from './types'

const BASE = '/api/v1/users'

export function followUser(username: string): Promise<FollowRelationship> {
  return request<FollowRelationship>(`${BASE}/${encodeURIComponent(username)}/follow`, {
    method: 'POST',
  })
}

export function unfollowUser(username: string): Promise<FollowRelationship> {
  return request<FollowRelationship>(`${BASE}/${encodeURIComponent(username)}/follow`, {
    method: 'DELETE',
  })
}

function withCursorParams(params: CursorPageParams): string {
  const query = new URLSearchParams()
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  return qs ? `?${qs}` : ''
}

export function getFollowers(
  username: string,
  params: CursorPageParams = {},
): Promise<FollowListResponse> {
  return request<FollowListResponse>(
    `${BASE}/${encodeURIComponent(username)}/followers${withCursorParams(params)}`,
  )
}

export function getFollowing(
  username: string,
  params: CursorPageParams = {},
): Promise<FollowListResponse> {
  return request<FollowListResponse>(
    `${BASE}/${encodeURIComponent(username)}/following${withCursorParams(params)}`,
  )
}
