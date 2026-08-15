import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Search screen integration tests (TSC-USER-002): debounced query,
 * loading/no-results/error/pagination states, and that a fast-typed later
 * query is what actually renders (no stale results from an earlier, slower
 * in-flight request). The search-mode strategy (prefix/exact/fuzzy) is an
 * internal implementation detail — never exposed as UI the user has to
 * choose between.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

async function goToSearch(user: ReturnType<typeof userEvent.setup>) {
  window.history.pushState({}, '', '/search')
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Search' })).toBeInTheDocument()
  return user
}

describe('Search', () => {
  it('prompts for a query before anything is typed', async () => {
    mockAuthenticatedSession()
    const user = userEvent.setup()
    await goToSearch(user)

    expect(screen.getByText('Search for people')).toBeInTheDocument()
  })

  it('shows loading skeletons while a search is in flight', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/search', async () => {
        await new Promise((resolve) => setTimeout(resolve, 100))
        return HttpResponse.json({
          data: [{ id: 'user-2', name: 'Alice', username: 'alice', bio: null, avatar_key: null }],
          page: { next_cursor: null },
        })
      }),
    )
    const user = userEvent.setup()
    await goToSearch(user)

    await user.type(screen.getByLabelText('Search people'), 'al')

    // While the (debounced, then in-flight) request is pending, loading
    // placeholders are shown instead of an empty/stale state.
    expect(await screen.findAllByRole('status', { name: 'Loading user' })).toHaveLength(3)
    expect(await screen.findByText('Alice')).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Loading user' })).not.toBeInTheDocument()
  })

  it('searches on typing (debounced) using prefix mode, without exposing that choice in the UI', async () => {
    mockAuthenticatedSession()
    let receivedMode: string | null = null
    server.use(
      http.get('*/api/v1/users/search', ({ request }) => {
        const url = new URL(request.url)
        receivedMode = url.searchParams.get('mode')
        return HttpResponse.json({
          data: [
            {
              id: 'user-2',
              name: 'Alice Prefix',
              username: 'alice',
              bio: 'Hi there.',
              avatar_key: null,
            },
          ],
          page: { next_cursor: null },
        })
      }),
    )
    const user = userEvent.setup()
    await goToSearch(user)

    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Search people'), 'al')

    expect(await screen.findByText('Alice Prefix')).toBeInTheDocument()
    await waitFor(() => expect(receivedMode).toBe('prefix'))
  })

  it('shows a no-results empty state', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/search', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    const user = userEvent.setup()
    await goToSearch(user)

    await user.type(screen.getByLabelText('Search people'), 'nobody')
    expect(await screen.findByText('No users found')).toBeInTheDocument()
  })

  it('shows an error state with retry on search failure', async () => {
    mockAuthenticatedSession()
    let attempts = 0
    server.use(
      http.get('*/api/v1/users/search', () => {
        attempts += 1
        return HttpResponse.json(
          { error: { code: 'internal_error', message: 'Search is temporarily unavailable.' } },
          { status: 500 },
        )
      }),
    )
    const user = userEvent.setup()
    await goToSearch(user)

    await user.type(screen.getByLabelText('Search people'), 'ada')
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Search is temporarily unavailable.')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(attempts).toBeGreaterThanOrEqual(2))
  })

  it('paginates results with a Load more button', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/search', ({ request }) => {
        const url = new URL(request.url)
        const cursor = url.searchParams.get('cursor')
        if (!cursor) {
          return HttpResponse.json({
            data: [
              { id: 'user-1', name: 'Page One', username: 'page_one', bio: null, avatar_key: null },
            ],
            page: { next_cursor: 'cursor-2' },
          })
        }
        return HttpResponse.json({
          data: [
            { id: 'user-2', name: 'Page Two', username: 'page_two', bio: null, avatar_key: null },
          ],
          page: { next_cursor: null },
        })
      }),
    )
    const user = userEvent.setup()
    await goToSearch(user)

    await user.type(screen.getByLabelText('Search people'), 'page')
    expect(await screen.findByText('Page One')).toBeInTheDocument()
    expect(screen.queryByText('Page Two')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Page Two')).toBeInTheDocument()
    expect(screen.getByText('Page One')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('a later, faster query is not overwritten by an earlier, slower one', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/search', async ({ request }) => {
        const url = new URL(request.url)
        const q = url.searchParams.get('q')
        if (q === 'a') {
          // Slow response for the first (abandoned) keystroke's query.
          await new Promise((resolve) => setTimeout(resolve, 150))
          return HttpResponse.json({
            data: [
              { id: 'stale', name: 'Stale Match', username: 'stale', bio: null, avatar_key: null },
            ],
            page: { next_cursor: null },
          })
        }
        return HttpResponse.json({
          data: [
            { id: 'fresh', name: 'Fresh Match', username: 'fresh', bio: null, avatar_key: null },
          ],
          page: { next_cursor: null },
        })
      }),
    )
    const user = userEvent.setup()
    await goToSearch(user)

    const input = screen.getByLabelText('Search people')
    await user.type(input, 'a')
    // Give the debounce a moment to fire the (slow) "a" request, then keep
    // typing before it resolves.
    await new Promise((resolve) => setTimeout(resolve, 50))
    await user.type(input, 'da')

    expect(await screen.findByText('Fresh Match')).toBeInTheDocument()
    // Wait past the slow "a" response's resolution time and confirm it never
    // clobbers the current (later) result.
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(screen.queryByText('Stale Match')).not.toBeInTheDocument()
    expect(screen.getByText('Fresh Match')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/search', () =>
        HttpResponse.json({
          data: [{ id: 'user-2', name: 'Alice', username: 'alice', bio: 'Hi.', avatar_key: null }],
          page: { next_cursor: null },
        }),
      ),
    )
    window.history.pushState({}, '', '/search')
    const user = userEvent.setup()
    const { container } = render(<App />)
    expect(await screen.findByRole('heading', { name: 'Search' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Search people'), 'al')
    await screen.findByText('Alice')

    expect(await axe(container)).toHaveNoViolations()
  })
})
