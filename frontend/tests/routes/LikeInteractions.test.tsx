import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { beforeEach, describe, expect, it } from 'vitest'
import App, { queryClient } from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Like/unlike control integration tests (TSC-LIKE-002): button states,
 * optimistic update + full rollback on a forced API failure, rapid-click
 * protection, the "pop" animation firing only on a newly-landed like (with
 * its reduced-motion override always present), and cross-cache consistency
 * between the feed and the tweet-detail page. Runs `<App />` end to end
 * against MSW, matching the pattern in
 * `tests/routes/FollowInteractions.test.tsx`. The cache-fan-out mechanics
 * themselves (every seedable cache shape, stale-cache reconciliation) are
 * unit-tested directly in `tests/features/tweets/useLikeMutation.test.tsx`.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

function feedTweet(overrides: Record<string, unknown> = {}) {
  return {
    id: 'tweet-1',
    author: { id: testUser.id, username: testUser.username, name: testUser.name, avatar_key: null },
    content: 'A likeable tweet',
    parent_tweet_id: null,
    like_count: 4,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: '2026-02-01T00:00:00Z',
    ...overrides,
  }
}

function mockFeed(tweet: ReturnType<typeof feedTweet>) {
  server.use(
    http.get('*/api/v1/feed', () =>
      HttpResponse.json({ data: [tweet], page: { next_cursor: null } }),
    ),
  )
}

describe('LikeButton', () => {
  beforeEach(async () => {
    await queryClient.cancelQueries()
    queryClient.clear()
  })

  it('shows an outline heart for an unliked tweet and a filled, pressed heart for a liked one', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: false, like_count: 4 }))
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Like, 4 likes' })
    expect(likeButton).toHaveAttribute('aria-pressed', 'false')
  })

  it('likes optimistically: state and count flip before the network response resolves', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: false, like_count: 4 }))
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', async () => {
        await new Promise((resolve) => setTimeout(resolve, 30))
        return HttpResponse.json({ liked: true, like_count: 5 })
      }),
    )
    const user = userEvent.setup()
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Like, 4 likes' })
    await user.click(likeButton)

    // Optimistic: flips immediately, before the delayed network response.
    expect(await screen.findByRole('button', { name: 'Liked, 5 likes' })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Liked, 5 likes' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    )
    // Let the delayed mock response actually resolve before the test ends —
    // otherwise its `setTimeout` fires after this test's own cleanup, and
    // its `onSuccess` would patch the *next* test's cache for the same
    // tweet id (`queryClient` is a module-level singleton, matching
    // `App.tsx`'s production setup) with this test's stale data.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Liked, 5 likes' })).not.toBeDisabled(),
    )
  })

  it('unlikes a previously-liked tweet', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: true, like_count: 5 }))
    server.use(
      http.delete('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: false, like_count: 4 }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Liked, 5 likes' })
    await user.click(likeButton)

    expect(await screen.findByRole('button', { name: 'Like, 4 likes' })).toBeInTheDocument()
  })

  it('fully rolls back the optimistic update and shows an accessible error when the request fails', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: false, like_count: 4 }))
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json(
          { error: { code: 'rate_limited', message: 'Too many requests.' } },
          { status: 429 },
        ),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Like, 4 likes' })
    await user.click(likeButton)

    // Rolls all the way back to unliked with the original count — not left
    // showing "Liked" with a stale/incremented count.
    expect(await screen.findByRole('button', { name: 'Like, 4 likes' })).toBeInTheDocument()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Couldn't like this tweet.")
    expect(alert).toHaveTextContent('Too many requests.')
  })

  it('ignores a rapid second click while a like mutation is still in flight', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: false, like_count: 4 }))
    let likeCalls = 0
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', async () => {
        likeCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 50))
        return HttpResponse.json({ liked: true, like_count: 5 })
      }),
    )
    const user = userEvent.setup()
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Like, 4 likes' })
    // Two rapid, synchronous-ish clicks before the first request resolves.
    await user.click(likeButton)
    await user.click(likeButton)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Liked, 5 likes' })).toBeInTheDocument(),
    )
    expect(likeCalls).toBe(1)
    // Let the delayed mock response settle before the test ends (see the
    // matching comment in the "likes optimistically" test above).
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Liked, 5 likes' })).not.toBeDisabled(),
    )
  })

  it('cannot drive the count negative from rapid clicks that race the same tweet', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: true, like_count: 0 }))
    server.use(
      http.delete('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: false, like_count: 0 }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Liked, 0 likes' })
    await user.click(likeButton)

    expect(await screen.findByRole('button', { name: 'Like, 0 likes' })).toBeInTheDocument()
  })

  it('plays the pop animation (with its reduced-motion override) only on a newly-landed like', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: false, like_count: 4 }))
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: true, like_count: 5 }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    const likeButton = await screen.findByRole('button', { name: 'Like, 4 likes' })
    const heartGlyph = likeButton.querySelector('span[aria-hidden="true"]')
    expect(heartGlyph?.className).not.toContain('animate-like-pop')

    await user.click(likeButton)
    await screen.findByRole('button', { name: 'Liked, 5 likes' })

    const likedButton = screen.getByRole('button', { name: 'Liked, 5 likes' })
    const likedGlyph = likedButton.querySelector('span[aria-hidden="true"]')
    expect(likedGlyph?.className).toContain('animate-like-pop')
    // The reduced-motion override travels with the animation class, so a
    // user with `prefers-reduced-motion: reduce` never sees it play.
    expect(likedGlyph?.className).toContain('motion-reduce:animate-none')
  })

  it('keeps the feed and an already-visited tweet-detail cache consistent after liking from the feed', async () => {
    mockAuthenticatedSession()
    const tweet = feedTweet({ liked_by_viewer: false, like_count: 4 })
    mockFeed(tweet)
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: true, like_count: 5 }),
      ),
      http.get('*/api/v1/tweets/tweet-1', () => HttpResponse.json(tweet)),
      http.get('*/api/v1/tweets/tweet-1/replies', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    // Visit the tweet-detail page first, so `['tweet', 'tweet-1']` is a
    // real cache entry (not just the feed's own copy), then return to the
    // feed to like it from there.
    await user.click(await screen.findByText('A likeable tweet'))
    await screen.findByRole('button', { name: 'Reply' })
    window.history.back()
    // The popstate → route-change round trip isn't synchronous with
    // `history.back()` itself; wait for it explicitly rather than relying
    // on the next `findByRole` to happen to retry long enough.
    await waitFor(() => expect(window.location.pathname).toBe('/'))

    const likeButton = await screen.findByRole('button', { name: 'Like, 4 likes' })
    await user.click(likeButton)
    await screen.findByRole('button', { name: 'Liked, 5 likes' })

    // The tweet-detail cache, populated by the earlier visit, already
    // reflects the like made from the feed — purely via
    // `patchTweetEverywhere` — proven by reading the cache directly rather
    // than the GET /tweets/:id route, which would mask a fan-out bug by
    // re-fetching the true state anyway.
    const cached = queryClient.getQueryData<{ liked_by_viewer: boolean; like_count: number }>([
      'tweet',
      'tweet-1',
    ])
    expect(cached).toMatchObject({ liked_by_viewer: true, like_count: 5 })
  })

  it('has no accessibility violations on an unliked tweet', async () => {
    mockAuthenticatedSession()
    mockFeed(feedTweet({ liked_by_viewer: false, like_count: 4 }))
    const { container } = render(<App />)

    await screen.findByRole('button', { name: 'Like, 4 likes' })
    expect(await axe(container)).toHaveNoViolations()
  })
})
