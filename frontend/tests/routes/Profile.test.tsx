import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Profile view integration tests (TSC-USER-002): own vs. other profile,
 * timeline rendering/pagination, and the "never expose email" acceptance
 * criterion. Runs `<App />` end to end against MSW, matching the pattern in
 * `tests/routes/auth-flow.test.tsx`.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

describe('Profile (own)', () => {
  it('renders the signed-in user profile with an edit affordance, a timeline, and never shows the email', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/ada/tweets', () =>
        HttpResponse.json({
          data: [
            {
              id: 'tweet-1',
              author_id: testUser.id,
              content: 'Hello, world!',
              parent_tweet_id: null,
              like_count: 2,
              reply_count: 0,
              created_at: '2026-02-01T00:00:00Z',
            },
          ],
          page: { next_cursor: null },
        }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    await user.click(screen.getByText('Signed in as @ada'))

    const heading = await screen.findByRole('heading', { name: 'Ada Lovelace' })
    const header = heading.closest('header') as HTMLElement
    expect(within(header).getByText('@ada')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit profile' })).toBeInTheDocument()
    expect(await screen.findByText('Hello, world!')).toBeInTheDocument()

    // Acceptance criterion: never expose email on a profile page.
    expect(document.body.textContent).not.toContain('ada@example.com')
  })

  it('shows an empty state when the profile has no tweets', async () => {
    mockAuthenticatedSession()
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    await user.click(screen.getByText('Signed in as @ada'))

    expect(await screen.findByText('No tweets yet')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    mockAuthenticatedSession()
    const user = userEvent.setup()
    const { container } = render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    await user.click(screen.getByText('Signed in as @ada'))
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    await screen.findByText('No tweets yet')

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('Profile (other user)', () => {
  it('shows another user’s public profile without an edit affordance', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/search', () =>
        HttpResponse.json({
          data: [
            {
              id: 'user-2',
              name: 'Bob Builder',
              username: 'bob',
              bio: 'Fixing things.',
              avatar_key: null,
            },
          ],
          page: { next_cursor: null },
        }),
      ),
      http.get('*/api/v1/users/bob', () =>
        HttpResponse.json({
          id: 'user-2',
          name: 'Bob Builder',
          username: 'bob',
          bio: 'Fixing things.',
          avatar_key: null,
          created_at: '2025-06-01T00:00:00Z',
          followers_count: 3,
          following_count: 1,
          is_following: false,
        }),
      ),
      http.get('*/api/v1/users/bob/tweets', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    const primaryNav = screen.getByRole('navigation', { name: 'Primary' })
    await user.click(within(primaryNav).getByRole('link', { name: /search/i }))
    await user.type(screen.getByLabelText('Search people'), 'bob')

    const result = await screen.findByText('Bob Builder')
    await user.click(result)

    expect(await screen.findByRole('heading', { name: 'Bob Builder' })).toBeInTheDocument()
    expect(screen.getByText('@bob')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit profile' })).not.toBeInTheDocument()
  })

  it('shows an error state with retry when the profile fails to load', async () => {
    mockAuthenticatedSession()
    let attempts = 0
    server.use(
      http.get('*/api/v1/users/missing', () => {
        attempts += 1
        return HttpResponse.json(
          { error: { code: 'not_found', message: 'User not found.' } },
          { status: 404 },
        )
      }),
    )
    window.history.pushState({}, '', '/profile/missing')
    const user = userEvent.setup()
    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('User not found.')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(attempts).toBeGreaterThanOrEqual(2))
  })
})
