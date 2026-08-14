import { http, HttpResponse } from 'msw'

// Wildcard origin: the app's `VITE_API_BASE_URL` is unset in tests, so
// requests go out as relative paths against jsdom's default origin. Matching
// on `*/path` makes these handlers origin-agnostic either way.
const API_BASE_URL = '*'

/** Default handlers: an "empty" backend with no valid session. Individual
 * tests override these with `server.use(...)` for specific scenarios
 * (successful login, session restore, refresh failures, etc.). */
export const handlers = [
  http.post(`${API_BASE_URL}/api/v1/auth/register`, () =>
    HttpResponse.json(
      {
        id: 'user-1',
        name: 'Ada Lovelace',
        username: 'ada',
        email: 'ada@example.com',
        bio: null,
        avatar_key: null,
        created_at: '2026-01-01T00:00:00Z',
      },
      { status: 201 },
    ),
  ),

  http.post(`${API_BASE_URL}/api/v1/auth/login`, () =>
    HttpResponse.json(
      { error: { code: 'unauthenticated', message: 'Invalid email or password.' } },
      { status: 401 },
    ),
  ),

  http.post(`${API_BASE_URL}/api/v1/auth/refresh`, () =>
    HttpResponse.json(
      { error: { code: 'unauthenticated', message: 'No session.' } },
      { status: 401 },
    ),
  ),

  http.post(`${API_BASE_URL}/api/v1/auth/logout`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API_BASE_URL}/api/v1/auth/me`, () =>
    HttpResponse.json(
      { error: { code: 'unauthenticated', message: 'Not authenticated.' } },
      { status: 401 },
    ),
  ),
]

export const testUser = {
  id: 'user-1',
  name: 'Ada Lovelace',
  username: 'ada',
  email: 'ada@example.com',
  bio: null,
  avatar_key: null,
  created_at: '2026-01-01T00:00:00Z',
}
