import { useAuthStore } from '../stores/auth-store'
import type { AccessTokenResponse, ApiErrorBody } from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
const REFRESH_PATH = '/api/v1/auth/refresh'

/** Typed error thrown by `request()` for any non-2xx response (spec §6.2). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: ApiErrorBody['error']['details']
  readonly requestId?: string

  constructor(status: number, body: ApiErrorBody['error'] | undefined) {
    super(body?.message ?? 'Request failed')
    this.name = 'ApiError'
    this.status = status
    this.code = body?.code ?? 'unknown_error'
    this.details = body?.details
    this.requestId = body?.request_id
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Attach the in-memory access token and allow 401 → refresh → retry. Auth
   * endpoints that must not recurse into the refresh flow pass `false`. */
  auth?: boolean
  /** Internal: prevents retrying the same request more than once. */
  _isRetry?: boolean
}

/** In-flight refresh promise, shared by every caller that hits a 401 at the
 * same time — guarantees at most one `/auth/refresh` call per outage
 * (acceptance criterion: "concurrent 401s cause at most one refresh"). */
let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = request<AccessTokenResponse>(REFRESH_PATH, { method: 'POST', auth: false })
      .then((data) => {
        useAuthStore.getState().setAccessToken(data.access_token)
        return data.access_token
      })
      .catch(() => {
        useAuthStore.getState().expireSession()
        return null
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

/** Typed fetch wrapper: JSON in/out, credentialed cookies for the refresh
 * flow, bearer auth from the in-memory store, and single-retry-after-refresh
 * on 401 (spec §7.1, §9.4). */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = true, _isRetry = false, body, headers, ...rest } = options

  const finalHeaders = new Headers(headers)
  let finalBody: BodyInit | undefined
  if (body !== undefined) {
    finalHeaders.set('Content-Type', 'application/json')
    finalBody = JSON.stringify(body)
  }
  if (auth) {
    const token = useAuthStore.getState().accessToken
    if (token) finalHeaders.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: finalBody,
    credentials: 'include',
  })

  if (response.status === 401 && auth && !_isRetry) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return request<T>(path, { ...options, _isRetry: true })
    }
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, (payload as ApiErrorBody | null)?.error)
  }

  return payload as T
}
