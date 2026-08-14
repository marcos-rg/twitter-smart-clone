import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { request } from '../../src/api/client'
import { useAuthStore } from '../../src/stores/auth-store'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

describe('Authentication end-to-end flows', () => {
  it('restores a valid session on load and renders the protected home route', async () => {
    mockAuthenticatedSession()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: 'Log in' })).not.toBeInTheDocument()
  })

  it('redirects to login when there is no valid session, and logging in reaches the protected route', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({
          access_token: 'fresh-token',
          token_type: 'bearer',
          expires_in: 900,
          user: testUser,
        }),
      ),
    )
    render(<App />)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct horse battery staple')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
  })

  it('registers a new account, then logs in with the pre-filled email', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({
          access_token: 'fresh-token',
          token_type: 'bearer',
          expires_in: 900,
          user: testUser,
        }),
      ),
    )
    render(<App />)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())
    await user.click(screen.getByRole('link', { name: 'Sign up' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument(),
    )
    await user.type(screen.getByLabelText('Name'), 'Ada Lovelace')
    await user.type(screen.getByLabelText('Username'), 'ada')
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct horse battery staple')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    // Registration redirects to login with the email pre-filled and a toast.
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())
    expect(screen.getByText('Account created. Log in to continue.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveValue('ada@example.com')

    await user.type(screen.getByLabelText('Password'), 'correct horse battery staple')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
  })

  it('logs out, clears auth state, and redirects to login', async () => {
    mockAuthenticatedSession()
    let logoutCalls = 0
    server.use(
      http.post('*/api/v1/auth/logout', () => {
        logoutCalls += 1
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Log out' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())
    expect(logoutCalls).toBe(1)
    expect(useAuthStore.getState().accessToken).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('never persists the access token to localStorage, sessionStorage, or a readable cookie', async () => {
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({
          access_token: 'super-secret-token',
          token_type: 'bearer',
          expires_in: 900,
          user: testUser,
        }),
      ),
    )
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct horse battery staple')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())
    expect(useAuthStore.getState().accessToken).toBe('super-secret-token')

    // The token lives only in the in-memory zustand store — never written to
    // any browser-persisted or JS-readable surface.
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
    expect(document.cookie).not.toContain('super-secret-token')
  })

  it('coalesces concurrent 401s into a single refresh call and retries each request once', async () => {
    useAuthStore.setState({ accessToken: 'stale-token', user: testUser, status: 'authenticated' })

    let protectedCallCount = 0
    let refreshCallCount = 0
    server.use(
      http.get('*/api/v1/protected-resource', () => {
        protectedCallCount += 1
        // First call per request fails with 401 until the token is rotated.
        return refreshCallCount === 0
          ? HttpResponse.json(
              { error: { code: 'unauthenticated', message: 'Expired.' } },
              { status: 401 },
            )
          : HttpResponse.json({ ok: true })
      }),
      http.post('*/api/v1/auth/refresh', () => {
        refreshCallCount += 1
        return HttpResponse.json({
          access_token: 'rotated-token',
          token_type: 'bearer',
          expires_in: 900,
        })
      }),
    )

    const [a, b] = await Promise.all([
      request<{ ok: boolean }>('/api/v1/protected-resource'),
      request<{ ok: boolean }>('/api/v1/protected-resource'),
    ])

    expect(refreshCallCount).toBe(1)
    expect(a).toEqual({ ok: true })
    expect(b).toEqual({ ok: true })
    // 2 initial 401s + 2 retries that now succeed.
    expect(protectedCallCount).toBe(4)
  })

  it('clears auth state and redirects to login without a loop when refresh fails', async () => {
    mockAuthenticatedSession()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Signed in as @ada')).toBeInTheDocument())

    let refreshAttempts = 0
    server.use(
      http.post('*/api/v1/auth/refresh', () => {
        refreshAttempts += 1
        return HttpResponse.json(
          { error: { code: 'unauthenticated', message: 'Refresh token invalid.' } },
          { status: 401 },
        )
      }),
      http.get('*/api/v1/protected-resource', () =>
        HttpResponse.json(
          { error: { code: 'unauthenticated', message: 'Expired.' } },
          { status: 401 },
        ),
      ),
    )

    // A protected request now hits a 401, triggers a failed refresh, and the
    // store should flip to unauthenticated exactly once.
    await expect(request('/api/v1/protected-resource')).rejects.toThrow()

    await waitFor(() => expect(useAuthStore.getState().status).toBe('unauthenticated'))
    expect(refreshAttempts).toBe(1)

    await waitFor(() =>
      expect(
        screen.getByText('Your session has expired. Please log in again.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()

    // No further automatic refresh attempts fire from the redirect itself.
    expect(refreshAttempts).toBe(1)
  })
})
