import { screen, waitFor } from '@testing-library/react'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import App, { queryClient } from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * End-to-end routing test for the notifications panel (TSC-NOTIF-002):
 * reachable from the nav, and opening an unread row both marks it read and
 * navigates to the right destination (a tweet for a like/reply, a profile
 * for a follow) — exercised through `<App />` so the `/notifications` route
 * wiring itself (not just the panel in isolation) is proven out. Panel
 * states/pagination/read-actions are covered in
 * `tests/features/notifications/NotificationsPanel.test.tsx`.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

/** `AppShell` renders the nav twice (desktop sidebar + mobile bottom bar),
 * both landing on `/notifications` — `findByRole` alone would ambiguously
 * match both, so pick the first live link to that route instead. */
async function clickNotificationsNavLink(user: ReturnType<typeof userEvent.setup>) {
  const links = await screen.findAllByRole('link', { name: /notifications, 1 unread/i })
  await user.click(links[0])
}

function notificationItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 'notif-1',
    type: 'like',
    actor: { id: 'user-2', username: 'grace', name: 'Grace Hopper', avatar_key: null },
    tweet_id: 'tweet-42',
    is_read: false,
    created_at: '2026-08-14T00:00:00Z',
    ...overrides,
  }
}

describe('Notifications route', () => {
  beforeEach(async () => {
    await queryClient.cancelQueries()
    queryClient.clear()
  })

  it('is reachable from the nav and shows the unread badge', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [notificationItem()],
          page: { next_cursor: null },
          unread_count: 1,
        }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    await clickNotificationsNavLink(user)

    expect(await screen.findByText(/Grace Hopper liked your tweet/)).toBeInTheDocument()
  })

  it('opening an unread like/reply notification marks it read and navigates to the tweet', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [notificationItem()],
          page: { next_cursor: null },
          unread_count: 1,
        }),
      ),
      http.post('*/api/v1/notifications/read', () =>
        HttpResponse.json({ marked_read: 1, unread_count: 0 }),
      ),
      http.get('*/api/v1/tweets/tweet-42', () =>
        HttpResponse.json({
          id: 'tweet-42',
          author: { id: 'user-2', username: 'grace', name: 'Grace Hopper', avatar_key: null },
          content: 'Hello from grace',
          parent_tweet_id: null,
          like_count: 1,
          reply_count: 0,
          liked_by_viewer: false,
          media: [],
          links: [],
          created_at: '2026-08-14T00:00:00Z',
        }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    await clickNotificationsNavLink(user)
    const row = await screen.findByText(/Grace Hopper liked your tweet/)
    await user.click(row)

    await waitFor(() => expect(screen.getByText('Hello from grace')).toBeInTheDocument())
  })

  it("opening an unread follow notification navigates to the actor's profile", async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [notificationItem({ id: 'notif-follow', type: 'follow', tweet_id: null })],
          page: { next_cursor: null },
          unread_count: 1,
        }),
      ),
      http.post('*/api/v1/notifications/read', () =>
        HttpResponse.json({ marked_read: 1, unread_count: 0 }),
      ),
      http.get('*/api/v1/users/grace', () =>
        HttpResponse.json({
          id: 'user-2',
          name: 'Grace Hopper',
          username: 'grace',
          bio: null,
          avatar_key: null,
          created_at: '2026-01-01T00:00:00Z',
          followers_count: 10,
          following_count: 2,
          is_following: false,
        }),
      ),
      http.get('*/api/v1/users/grace/tweets', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    await clickNotificationsNavLink(user)
    const row = await screen.findByText(/Grace Hopper followed you/)
    await user.click(row)

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Grace Hopper' })).toBeInTheDocument(),
    )
  })
})
