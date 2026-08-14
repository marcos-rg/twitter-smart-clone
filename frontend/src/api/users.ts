import { request } from './client'
import type {
  SearchMode,
  UserPrivateProfile,
  UserProfileUpdateRequest,
  UserPublicProfile,
  UserSearchResponse,
  UserTimelineResponse,
} from './types'

const BASE = '/api/v1/users'

export function getProfile(username: string): Promise<UserPublicProfile> {
  return request<UserPublicProfile>(`${BASE}/${encodeURIComponent(username)}`)
}

export function updateMyProfile(payload: UserProfileUpdateRequest): Promise<UserPrivateProfile> {
  return request<UserPrivateProfile>(`${BASE}/me`, { method: 'PATCH', body: payload })
}

export interface CursorPageParams {
  cursor?: string
  limit?: number
}

export function getUserTweets(
  username: string,
  params: CursorPageParams = {},
): Promise<UserTimelineResponse> {
  const query = new URLSearchParams()
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  return request<UserTimelineResponse>(
    `${BASE}/${encodeURIComponent(username)}/tweets${qs ? `?${qs}` : ''}`,
  )
}

export interface SearchUsersParams extends CursorPageParams {
  q: string
  mode: SearchMode
}

export function searchUsers({
  q,
  mode,
  cursor,
  limit,
}: SearchUsersParams): Promise<UserSearchResponse> {
  const query = new URLSearchParams({ q, mode })
  if (cursor) query.set('cursor', cursor)
  if (limit) query.set('limit', String(limit))
  return request<UserSearchResponse>(`${BASE}/search?${query.toString()}`)
}
