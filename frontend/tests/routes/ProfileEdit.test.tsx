import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Profile-edit integration tests (TSC-USER-002): validation mirrors the
 * backend, a successful save updates the header/nav, a 409 conflict
 * preserves the user's entered values instead of resetting the form, and
 * editing someone else's profile is impossible via direct navigation.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

async function goToEditScreen(user: ReturnType<typeof userEvent.setup>) {
  render(<App />)
  await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
  await user.click(screen.getByText('Signed in as @ada'))
  await user.click(await screen.findByRole('button', { name: 'Edit profile' }))
  expect(await screen.findByRole('heading', { name: 'Edit profile' })).toBeInTheDocument()
}

describe('ProfileEdit', () => {
  it('shows inline validation errors mirroring backend rules and does not submit', async () => {
    mockAuthenticatedSession()
    const user = userEvent.setup()
    await goToEditScreen(user)

    await user.clear(screen.getByLabelText('Username'))
    await user.type(screen.getByLabelText('Username'), 'a')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(
      screen.getByText('Username must be 3-30 characters: letters, numbers, and underscores only.'),
    ).toBeInTheDocument()
  })

  it('saves valid edits and navigates to the (possibly renamed) profile', async () => {
    mockAuthenticatedSession()
    server.use(
      http.patch('*/api/v1/users/me', async ({ request }) => {
        const body = (await request.json()) as Record<string, string>
        return HttpResponse.json({ ...testUser, ...body })
      }),
      http.get('*/api/v1/users/ada_updated', () =>
        HttpResponse.json({
          id: testUser.id,
          name: 'Ada Updated',
          username: 'ada_updated',
          bio: 'Updated bio.',
          avatar_key: null,
          created_at: testUser.created_at,
        }),
      ),
      http.get('*/api/v1/users/ada_updated/tweets', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    const user = userEvent.setup()
    await goToEditScreen(user)

    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Ada Updated')
    await user.clear(screen.getByLabelText('Username'))
    await user.type(screen.getByLabelText('Username'), 'ada_updated')
    await user.type(screen.getByLabelText('Bio'), 'Updated bio.')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Profile updated.')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Ada Updated' })).toBeInTheDocument()
    expect(screen.getByText('@ada_updated')).toBeInTheDocument()
  })

  it('preserves the entered values when the server reports a username conflict', async () => {
    mockAuthenticatedSession()
    server.use(
      http.patch('*/api/v1/users/me', () =>
        HttpResponse.json(
          { error: { code: 'conflict', message: 'Username is already taken.' } },
          { status: 409 },
        ),
      ),
    )
    const user = userEvent.setup()
    await goToEditScreen(user)

    await user.clear(screen.getByLabelText('Username'))
    await user.type(screen.getByLabelText('Username'), 'taken_username')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Username is already taken.')).toBeInTheDocument()
    // The field keeps exactly what the user typed — it was not reset back to
    // the pre-edit server value.
    expect(screen.getByLabelText('Username')).toHaveValue('taken_username')
  })

  it('redirects to the read-only profile when navigating to edit someone else’s profile', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/users/bob', () =>
        HttpResponse.json({
          id: 'user-2',
          name: 'Bob Builder',
          username: 'bob',
          bio: null,
          avatar_key: null,
          created_at: '2025-06-01T00:00:00Z',
        }),
      ),
      http.get('*/api/v1/users/bob/tweets', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/profile/bob/edit')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Bob Builder' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Edit profile' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit profile' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    mockAuthenticatedSession()
    const user = userEvent.setup()
    const { container } = render(<App />)
    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    await user.click(screen.getByText('Signed in as @ada'))
    await user.click(await screen.findByRole('button', { name: 'Edit profile' }))
    await screen.findByRole('heading', { name: 'Edit profile' })

    expect(await axe(container)).toHaveNoViolations()
  })
})
