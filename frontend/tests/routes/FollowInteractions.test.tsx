import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Follow/unfollow control and follower/following list integration tests
 * (TSC-SOC-002): control states for self/followed/unfollowed profiles,
 * optimistic update + rollback on a forced API failure, rapid-click
 * protection against contradictory concurrent mutations, and paginated
 * list navigation. Runs `<App />` end to end against MSW, matching the
 * pattern in `tests/routes/Profile.test.tsx`.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

const bob = {
  id: 'user-2',
  name: 'Bob Builder',
  username: 'bob',
  bio: 'Fixing things.',
  avatar_key: null,
  created_at: '2025-06-01T00:00:00Z',
}

function mockBobProfile(
  overrides: Partial<
    typeof bob & { followers_count: number; following_count: number; is_following: boolean }
  > = {},
) {
  server.use(
    http.get('*/api/v1/users/bob', () =>
      HttpResponse.json({
        ...bob,
        followers_count: 4,
        following_count: 2,
        is_following: false,
        ...overrides,
      }),
    ),
    http.get('*/api/v1/users/bob/tweets', () =>
      HttpResponse.json({ data: [], page: { next_cursor: null } }),
    ),
  )
}

describe('FollowButton', () => {
  it('renders no follow control on your own profile', async () => {
    mockAuthenticatedSession()
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    await user.click(screen.getByText('Signed in as @ada'))

    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    expect(screen.queryByRole('button', { name: 'Follow' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Following' })).not.toBeInTheDocument()
  })

  it('shows a "Follow" control for an unfollowed profile and follows optimistically', async () => {
    mockAuthenticatedSession()
    mockBobProfile({ is_following: false, followers_count: 4 })
    server.use(
      http.post('*/api/v1/users/bob/follow', () =>
        HttpResponse.json({ following: true, followers_count: 5 }),
      ),
    )
    window.history.pushState({}, '', '/profile/bob')
    const user = userEvent.setup()
    render(<App />)

    const followButton = await screen.findByRole('button', { name: 'Follow' })
    await user.click(followButton)

    // Optimistic: flips immediately, before the network response resolves.
    expect(await screen.findByRole('button', { name: 'Following' })).toBeInTheDocument()
    expect(await screen.findByText('5')).toBeInTheDocument()
  })

  it('shows a "Following" control for an already-followed profile', async () => {
    mockAuthenticatedSession()
    mockBobProfile({ is_following: true, followers_count: 4 })
    window.history.pushState({}, '', '/profile/bob')
    render(<App />)

    const followButton = await screen.findByRole('button', { name: 'Following' })
    expect(followButton).toHaveAttribute('aria-pressed', 'true')
  })

  it('fully rolls back the optimistic update when the follow request fails', async () => {
    mockAuthenticatedSession()
    mockBobProfile({ is_following: false, followers_count: 4 })
    server.use(
      http.post('*/api/v1/users/bob/follow', () =>
        HttpResponse.json(
          { error: { code: 'rate_limited', message: 'Too many requests.' } },
          { status: 429 },
        ),
      ),
    )
    window.history.pushState({}, '', '/profile/bob')
    const user = userEvent.setup()
    render(<App />)

    const followButton = await screen.findByRole('button', { name: 'Follow' })
    expect(screen.getByText('4')).toBeInTheDocument()
    await user.click(followButton)

    // Rolls all the way back to "Follow" and the original count — not left
    // showing "Following" with a stale/incremented count.
    expect(await screen.findByRole('button', { name: 'Follow' })).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('ignores a rapid second click while a follow mutation is still in flight', async () => {
    mockAuthenticatedSession()
    mockBobProfile({ is_following: false, followers_count: 4 })
    let followCalls = 0
    server.use(
      http.post('*/api/v1/users/bob/follow', async () => {
        followCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 50))
        return HttpResponse.json({ following: true, followers_count: 5 })
      }),
    )
    window.history.pushState({}, '', '/profile/bob')
    const user = userEvent.setup()
    render(<App />)

    const followButton = await screen.findByRole('button', { name: 'Follow' })
    // Two rapid, synchronous-ish clicks before the first request resolves.
    await user.click(followButton)
    await user.click(followButton)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Following' })).toBeInTheDocument(),
    )
    expect(followCalls).toBe(1)
  })

  it('has no accessibility violations on an unfollowed profile', async () => {
    mockAuthenticatedSession()
    mockBobProfile({ is_following: false })
    window.history.pushState({}, '', '/profile/bob')
    const { container } = render(<App />)

    await screen.findByRole('button', { name: 'Follow' })
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('Followers / Following lists', () => {
  const followersPage1 = [
    { id: 'user-10', name: 'Grace Hopper', username: 'ghopper', bio: null, avatar_key: null },
    { id: 'user-11', name: 'Alan Turing', username: 'turing', bio: null, avatar_key: null },
  ]
  const followersPage2 = [
    { id: 'user-12', name: 'Katherine Johnson', username: 'kjohnson', bio: null, avatar_key: null },
  ]

  it('navigates from a profile to its followers list via the count link', async () => {
    mockAuthenticatedSession()
    mockBobProfile({ followers_count: 2 })
    server.use(
      http.get('*/api/v1/users/bob/followers', () =>
        HttpResponse.json({ data: followersPage1, page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/profile/bob')
    const user = userEvent.setup()
    render(<App />)

    await screen.findByRole('heading', { name: 'Bob Builder' })
    await user.click(screen.getByRole('link', { name: /followers/i }))

    expect(await screen.findByRole('heading', { name: 'Followers' })).toBeInTheDocument()
    expect(await screen.findByText('Grace Hopper')).toBeInTheDocument()
    expect(screen.getByText('Alan Turing')).toBeInTheDocument()
  })

  it('paginates without duplicating users and switches tabs without losing state', async () => {
    mockAuthenticatedSession()
    let cursorRequested: string | null = null
    // Uses a distinct username ("carol") from the rest of this describe
    // block so its `['followers', 'carol']` / `['following', 'carol']` query
    // cache entries can't be seeded by an earlier test's `['followers',
    // 'bob']` fetch — the app's `QueryClient` is a module-level singleton
    // shared across tests in this file (matching `App.tsx`'s production
    // setup), so cross-test cache bleed is otherwise possible for a
    // repeated username.
    server.use(
      http.get('*/api/v1/users/carol/followers', ({ request }) => {
        const url = new URL(request.url)
        const cursor = url.searchParams.get('cursor')
        if (cursor) {
          cursorRequested = cursor
          return HttpResponse.json({ data: followersPage2, page: { next_cursor: null } })
        }
        return HttpResponse.json({ data: followersPage1, page: { next_cursor: 'cursor-1' } })
      }),
      http.get('*/api/v1/users/carol/following', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/profile/carol/followers')
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('Grace Hopper')
    await user.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Katherine Johnson')).toBeInTheDocument()
    expect(cursorRequested).toBe('cursor-1')
    // No duplicate rows: each username still appears exactly once.
    expect(screen.getAllByText('Grace Hopper')).toHaveLength(1)

    // Switching to "Following" and back to "Followers" preserves the
    // already-fetched second page instead of resetting to page one.
    await user.click(screen.getByRole('link', { name: 'Following' }))
    await screen.findByRole('heading', { name: 'Following' })
    await user.click(screen.getByRole('link', { name: 'Followers' }))

    expect(await screen.findByText('Katherine Johnson')).toBeInTheDocument()
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument()
  })

  it('shows an empty state when a user has no followers', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/bob/followers', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/profile/bob/followers')
    render(<App />)

    expect(await screen.findByText('No followers')).toBeInTheDocument()
  })

  it('shows an error state with retry when the followers list fails to load', async () => {
    mockAuthenticatedSession()
    let attempts = 0
    server.use(
      http.get('*/api/v1/users/bob/followers', () => {
        attempts += 1
        return HttpResponse.json(
          { error: { code: 'internal_error', message: 'Something broke.' } },
          { status: 500 },
        )
      }),
    )
    window.history.pushState({}, '', '/profile/bob/followers')
    const user = userEvent.setup()
    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Something broke.')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(attempts).toBeGreaterThanOrEqual(2))
  })

  it('has no accessibility violations on the followers list', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/bob/followers', () =>
        HttpResponse.json({ data: followersPage1, page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/profile/bob/followers')
    const { container } = render(<App />)

    await screen.findByText('Grace Hopper')
    expect(await axe(container)).toHaveNoViolations()
  })
})
