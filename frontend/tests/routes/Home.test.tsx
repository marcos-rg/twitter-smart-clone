import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Home route integration tests (TSC-FEED-002): the authenticated `/` route
 * renders the feed behind the existing header/log-out scaffold, and the
 * approved scroll-restoration policy holds across a real browser
 * navigation to a tweet's detail page and back.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

function feedTweet(id: string, createdAt: string) {
  return {
    id,
    author: { id: testUser.id, username: testUser.username, name: testUser.name, avatar_key: null },
    content: `Feed tweet ${id}`,
    parent_tweet_id: null,
    like_count: 0,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: createdAt,
  }
}

describe('Home', () => {
  it('renders the feed for the signed-in user, alongside the existing header', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/feed', () =>
        HttpResponse.json({
          data: [feedTweet('tweet-1', '2026-02-01T00:00:00Z')],
          page: { next_cursor: null },
        }),
      ),
    )
    render(<App />)

    expect(await screen.findByText('Signed in as @ada')).toBeInTheDocument()
    expect(await screen.findByText('Feed tweet tweet-1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument()
  })

  it('restores scroll position when returning to the feed via back navigation, but not on a fresh visit', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/feed', () =>
        HttpResponse.json({
          data: [feedTweet('tweet-1', '2026-02-01T00:00:00Z')],
          page: { next_cursor: null },
        }),
      ),
      http.get('*/api/v1/tweets/tweet-1', () =>
        HttpResponse.json(feedTweet('tweet-1', '2026-02-01T00:00:00Z')),
      ),
      http.get('*/api/v1/tweets/tweet-1/replies', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    const tweetLink = await screen.findByText('Feed tweet tweet-1')

    // Simulate having scrolled the feed down before navigating away.
    window.scrollTo(0, 400)
    await waitFor(() => expect(window.scrollY).toBe(400))

    await user.click(tweetLink)
    await screen.findByRole('button', { name: 'Reply' })

    window.history.back()

    await screen.findByText('Feed tweet tweet-1')
    await waitFor(() => expect(window.scrollY).toBe(400))

    // A fresh (non-back) arrival at the feed — e.g. clicking the "Home" nav
    // link again — resets to the top rather than replaying a stale saved
    // position from the earlier visit.
    window.scrollTo(0, 250)
    const primaryNav = screen.getByRole('navigation', { name: 'Primary' })
    await user.click(within(primaryNav).getByRole('link', { name: /search/i }))
    await screen.findByLabelText('Search people')

    await user.click(within(primaryNav).getByRole('link', { name: /home/i }))
    await screen.findByText('Feed tweet tweet-1')
    await waitFor(() => expect(window.scrollY).toBe(0))
  })
})
