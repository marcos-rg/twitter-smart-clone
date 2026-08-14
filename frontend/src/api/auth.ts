import { request } from './client'
import type { AccessTokenResponse, LoginPayload, RegisterPayload, UserPublic } from './types'

const BASE = '/api/v1/auth'

export function register(payload: RegisterPayload): Promise<UserPublic> {
  return request<UserPublic>(`${BASE}/register`, { method: 'POST', body: payload, auth: false })
}

export function login(payload: LoginPayload): Promise<AccessTokenResponse> {
  return request<AccessTokenResponse>(`${BASE}/login`, {
    method: 'POST',
    body: payload,
    auth: false,
  })
}

/** Rotates the httpOnly refresh cookie for a new access token. Called both by
 * the 401 interceptor and on app boot to restore a session. */
export function refresh(): Promise<AccessTokenResponse> {
  return request<AccessTokenResponse>(`${BASE}/refresh`, { method: 'POST', auth: false })
}

export function logout(): Promise<void> {
  return request<void>(`${BASE}/logout`, { method: 'POST' })
}

export function getCurrentUser(): Promise<UserPublic> {
  return request<UserPublic>(`${BASE}/me`)
}
