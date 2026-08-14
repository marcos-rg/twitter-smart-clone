import {
  test,
  expect,
  uniqueUser,
  registerViaUi,
  loginViaUi,
  expectAuthenticated,
  expectOnLoginScreen,
} from './fixtures'

/**
 * Full-stack auth E2E suite (`TSC-AUTH-003`): register, login, protected
 * navigation, reload/refresh, logout, invalid credentials, expired access
 * token recovery, revoked refresh token, and duplicate user — run against
 * the real containerized stack (`frontend` dev server -> `backend` ->
 * real PostgreSQL + Redis), not mocks. Requires the stack already running
 * (`make up`, or the `auth-e2e` CI job) — see `playwright.auth.config.ts`.
 *
 * Every test also gets the automatic no-console-error /
 * no-failed-request / no-token-leak assertions from `fixtures.ts`'s
 * extended `test`.
 */

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://localhost:8000'

test.describe('Register', () => {
  test('creates an account and routes to login without starting a session', async ({ page }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)

    await expect(page.getByText('Account created. Log in to continue.')).toBeVisible()
    // Registration never issues tokens (spec §7.1): the email field is
    // pre-filled but the user must still authenticate explicitly.
    await expect(page.getByLabel('Email')).toHaveValue(user.email)
  })
})

test.describe('Duplicate user', () => {
  test('registering the same username/email twice is rejected, not silently accepted', async ({
    page,
  }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)

    await page.goto('/register')
    await page.getByLabel('Name', { exact: true }).fill(user.name)
    await page.getByLabel('Username').fill(user.username)
    await page.getByLabel('Email').fill(user.email)
    await page.getByLabel('Password').fill(user.password)
    await page.getByRole('button', { name: 'Create account' }).click()

    const alert = page.getByRole('alert')
    await expect(alert).toBeVisible()
    await expect(alert).toContainText(/already/i)
    // Still on the registration screen -- the duplicate attempt did not
    // silently succeed or navigate anywhere.
    await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible()
  })
})

test.describe('Invalid credentials', () => {
  test('wrong password shows a generic error and does not authenticate', async ({ page }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)

    await page.getByLabel('Password').fill('definitely-the-wrong-password')
    await page.getByRole('button', { name: 'Log in' }).click()

    const alert = page.getByRole('alert')
    await expect(alert).toBeVisible()
    await expect(alert.locator('span')).toHaveText('Invalid email or password.')
    await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
  })

  test('unknown email shows the same generic error (no user enumeration)', async ({ page }) => {
    const user = uniqueUser()
    await page.goto('/login')
    await page.getByLabel('Email').fill(user.email)
    await page.getByLabel('Password').fill('whatever-password-123')
    await page.getByRole('button', { name: 'Log in' }).click()

    const alert = page.getByRole('alert')
    await expect(alert).toBeVisible()
    await expect(alert.locator('span')).toHaveText('Invalid email or password.')
  })
})

test.describe('Login and protected navigation', () => {
  test('login reaches the protected home route; the auth screens redirect away once signed in', async ({
    page,
  }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)
    await loginViaUi(page, user)
    await expectAuthenticated(page, user.username)

    // PublicOnlyRoute: an authenticated user is bounced off /login and
    // /register back to the protected home route.
    await page.goto('/login')
    await expectAuthenticated(page, user.username)

    await page.goto('/register')
    await expectAuthenticated(page, user.username)
  })
})

test.describe('Reload / session restoration', () => {
  test('an authenticated session survives a full page reload', async ({ page }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)
    await loginViaUi(page, user)
    await expectAuthenticated(page, user.username)

    await page.reload()

    // The reload re-mounts the app with no in-memory state at all -- only
    // the httpOnly refresh cookie restores the session (POST /auth/refresh
    // + GET /auth/me), so this proves the cookie-based restoration path
    // works end to end against the real backend.
    await expectAuthenticated(page, user.username)
  })
})

test.describe('Logout', () => {
  test('logout clears the session and a subsequent visit requires login again', async ({
    page,
  }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)
    await loginViaUi(page, user)
    await expectAuthenticated(page, user.username)

    await page.getByRole('button', { name: 'Log out' }).click()
    await expectOnLoginScreen(page)

    // No leftover session: revisiting the protected route (even with a
    // reload, forcing a fresh cookie-based restore attempt) lands on login.
    await page.goto('/')
    await expectOnLoginScreen(page)
  })
})

test.describe('Expired access token recovery', () => {
  test('an invalidated in-memory access token is recovered transparently via refresh', async ({
    page,
  }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)
    await loginViaUi(page, user)
    await expectAuthenticated(page, user.username)

    // Simulate the access token having expired by the time the next
    // authenticated request goes out: intercept exactly one outgoing
    // GET /auth/me and corrupt its Authorization header before it reaches
    // the (real) backend. The backend rejects an expired token and an
    // invalid/corrupted one identically (401 "Invalid or expired access
    // token"), and the client's recovery code path (single-flight refresh
    // + one retry, in `src/api/client.ts`) doesn't distinguish between the
    // two either -- so this exercises the exact production recovery logic
    // against a real 401 from the real backend, without waiting out the
    // real 15-minute access-token lifetime.
    let corrupted = false
    await page.route('**/api/v1/auth/me', async (route) => {
      const request = route.request()
      if (!corrupted) {
        corrupted = true
        await route.continue({
          headers: { ...request.headers(), authorization: 'Bearer invalid.expired.token' },
        })
        return
      }
      await route.continue()
    })

    // The session-bootstrap effect (refresh cookie -> GET /auth/me) runs
    // again on reload, giving us a real authenticated request to intercept.
    await page.reload()

    // Recovery is transparent: the app never shows a login screen or an
    // error toast, and ends up authenticated as the same user, having
    // silently refreshed once behind the scenes.
    await expectAuthenticated(page, user.username)
    await expect(page.getByRole('alert')).toHaveCount(0)

    await page.unroute('**/api/v1/auth/me')
  })
})

test.describe('Revoked refresh token (reuse detection)', () => {
  test('replaying an already-rotated refresh token revokes the whole token family', async ({
    page,
  }) => {
    const user = uniqueUser()
    await registerViaUi(page, user)
    await loginViaUi(page, user)
    await expectAuthenticated(page, user.username)

    const cookiesBefore = await page.context().cookies()
    const originalRefreshCookie = cookiesBefore.find((c) => c.name === 'refresh_token')
    expect(originalRefreshCookie, 'refresh_token cookie must be set after login').toBeTruthy()

    // Reload rotates the refresh cookie (spec: "every /auth/refresh issues a
    // new refresh token and revokes the old one").
    await page.reload()
    await expectAuthenticated(page, user.username)

    const cookiesAfter = await page.context().cookies()
    const rotatedRefreshCookie = cookiesAfter.find((c) => c.name === 'refresh_token')
    expect(
      rotatedRefreshCookie,
      'refresh_token cookie must still be set after rotation',
    ).toBeTruthy()
    expect(rotatedRefreshCookie!.value).not.toBe(originalRefreshCookie!.value)

    // Replay the original (now-stale, already-rotated) refresh token
    // directly against the API, simulating a stolen cookie being reused --
    // the backend must reject it (401) rather than accept it.
    await page.context().addCookies([
      {
        name: 'refresh_token',
        value: originalRefreshCookie!.value,
        domain: 'localhost',
        path: '/api/v1/auth',
        httpOnly: true,
        secure: false,
        sameSite: 'Strict',
      },
    ])
    const replayResponse = await page.request.post(`${API_BASE_URL}/api/v1/auth/refresh`)
    expect(replayResponse.status()).toBe(401)

    // Restore the legitimately-rotated cookie the client itself is still
    // holding, and confirm reuse detection revoked the *entire* family --
    // even this previously-valid token no longer restores a session, so a
    // reload now requires logging in again.
    await page.context().addCookies([
      {
        name: 'refresh_token',
        value: rotatedRefreshCookie!.value,
        domain: 'localhost',
        path: '/api/v1/auth',
        httpOnly: true,
        secure: false,
        sameSite: 'Strict',
      },
    ])
    await page.reload()
    await expectOnLoginScreen(page)
  })
})
