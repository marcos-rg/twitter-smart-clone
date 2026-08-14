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

  // `/users/*` defaults: `testUser`'s public profile resolves, editing it
  // echoes the submitted fields back, and timeline/search start empty.
  // Individual tests override these with `server.use(...)` for conflicts,
  // other users' profiles, search results, pagination, and error scenarios.
  http.get(`${API_BASE_URL}/api/v1/users/:username`, ({ params }) => {
    const username = String(params.username)
    if (username.toLowerCase() !== testUser.username.toLowerCase()) {
      return HttpResponse.json(
        { error: { code: 'not_found', message: 'User not found.' } },
        { status: 404 },
      )
    }
    const publicProfile = {
      id: testUser.id,
      name: testUser.name,
      username: testUser.username,
      bio: testUser.bio,
      avatar_key: testUser.avatar_key,
      created_at: testUser.created_at,
      followers_count: 0,
      following_count: 0,
      is_following: false,
    }
    return HttpResponse.json(publicProfile)
  }),

  http.patch(`${API_BASE_URL}/api/v1/users/me`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>
    return HttpResponse.json({ ...testUser, ...body })
  }),

  http.get(`${API_BASE_URL}/api/v1/users/:username/tweets`, () =>
    HttpResponse.json({ data: [], page: { next_cursor: null } }),
  ),

  http.get(`${API_BASE_URL}/api/v1/users/search`, () =>
    HttpResponse.json({ data: [], page: { next_cursor: null } }),
  ),

  // `/users/:username/follow`, `/followers`, `/following` defaults: follow
  // succeeds idempotently and lists start empty. Individual tests override
  // with `server.use(...)` for forced-failure and populated-list scenarios.
  http.post(`${API_BASE_URL}/api/v1/users/:username/follow`, () =>
    HttpResponse.json({ following: true, followers_count: 1 }),
  ),

  http.delete(`${API_BASE_URL}/api/v1/users/:username/follow`, () =>
    HttpResponse.json({ following: false, followers_count: 0 }),
  ),

  http.get(`${API_BASE_URL}/api/v1/users/:username/followers`, () =>
    HttpResponse.json({ data: [], page: { next_cursor: null } }),
  ),

  http.get(`${API_BASE_URL}/api/v1/users/:username/following`, () =>
    HttpResponse.json({ data: [], page: { next_cursor: null } }),
  ),

  // `/tweets/*` defaults (TSC-TWEET-002): creating a tweet/reply echoes a
  // well-formed `TweetView` back (authored by `testUser`); getting/listing
  // an unseeded tweet 404s / returns an empty page. Individual tests
  // override these with `server.use(...)` for populated fixtures, replies,
  // and error scenarios.
  http.post(`${API_BASE_URL}/api/v1/tweets`, async ({ request }) => {
    const body = (await request.json()) as {
      content: string
      parent_tweet_id?: string | null
      media_keys?: string[]
    }
    return HttpResponse.json(
      {
        id: 'tweet-new',
        author: {
          id: testUser.id,
          username: testUser.username,
          name: testUser.name,
          avatar_key: testUser.avatar_key,
        },
        content: body.content.trim(),
        parent_tweet_id: body.parent_tweet_id ?? null,
        like_count: 0,
        reply_count: 0,
        liked_by_viewer: false,
        media: (body.media_keys ?? []).map((key, position) => ({
          key,
          content_type: 'image/png',
          position,
        })),
        links: [],
        created_at: '2026-02-01T00:00:00Z',
      },
      { status: 201 },
    )
  }),

  http.get(`${API_BASE_URL}/api/v1/tweets/:tweetId`, () =>
    HttpResponse.json(
      { error: { code: 'not_found', message: 'Tweet not found.' } },
      { status: 404 },
    ),
  ),

  http.get(`${API_BASE_URL}/api/v1/tweets/:tweetId/replies`, () =>
    HttpResponse.json({ data: [], page: { next_cursor: null } }),
  ),

  // `/tweets/:tweetId/like` defaults (TSC-LIKE-002): like/unlike succeed
  // idempotently. Individual tests override with `server.use(...)` for
  // specific counts and forced-failure scenarios.
  http.post(`${API_BASE_URL}/api/v1/tweets/:tweetId/like`, () =>
    HttpResponse.json({ liked: true, like_count: 1 }),
  ),

  http.delete(`${API_BASE_URL}/api/v1/tweets/:tweetId/like`, () =>
    HttpResponse.json({ liked: false, like_count: 0 }),
  ),

  // `/feed` default (TSC-FEED-002): empty home feed. Individual tests
  // override with `server.use(...)` for populated/paginated/error fixtures.
  http.get(`${API_BASE_URL}/api/v1/feed`, () =>
    HttpResponse.json({ data: [], page: { next_cursor: null } }),
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
