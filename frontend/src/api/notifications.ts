import { request } from './client'
import type { CursorPageParams } from './users'
import type {
  NotificationListResponse,
  NotificationMarkReadRequest,
  NotificationMarkReadResponse,
} from './types'

const BASE = '/api/v1/notifications'

/** `GET /notifications` — the caller's notifications, newest first,
 * cursor-paginated, plus a top-level `unread_count` (TSC-NOTIF-001). */
export function listNotifications(
  params: CursorPageParams = {},
): Promise<NotificationListResponse> {
  const query = new URLSearchParams()
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  return request<NotificationListResponse>(`${BASE}${qs ? `?${qs}` : ''}`)
}

/** `POST /notifications/read` — mark all (omit/`null` body) or a selected
 * set of notifications as read. Idempotent either way. */
export function markNotificationsRead(
  body: NotificationMarkReadRequest = {},
): Promise<NotificationMarkReadResponse> {
  return request<NotificationMarkReadResponse>(`${BASE}/read`, { method: 'POST', body })
}

/** Derives the `GET /api/v1/ws` URL from the same base the REST client uses
 * (`VITE_API_BASE_URL`, empty string ⇒ same-origin), swapping the
 * `http(s)` scheme for `ws(s)` — no separate env var needed since the
 * WebSocket endpoint lives on the same host/port as the REST API. */
export function websocketUrl(accessToken: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
  const origin = base || (typeof window !== 'undefined' ? window.location.origin : '')
  const wsOrigin = origin.replace(/^http/, 'ws')
  return `${wsOrigin}/api/v1/ws?token=${encodeURIComponent(accessToken)}`
}
