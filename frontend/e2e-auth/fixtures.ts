import { test as base, expect, type Page } from '@playwright/test'

/**
 * Shared fixtures/helpers for the auth E2E suite (`TSC-AUTH-003`), run
 * against the real containerized stack (real PostgreSQL + Redis behind the
 * `backend` container, per `playwright.auth.config.ts`).
 */

/** Generates a fresh, collision-free user for each test: unique username
 * (letters/digits/underscore only, per `USERNAME_PATTERN`) and email so
 * tests never depend on (or pollute) a shared fixture user, and can run
 * against a Postgres volume that persists across local/CI runs. */
export function uniqueUser() {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`
  return {
    name: 'E2E Test User',
    username: `e2e_${suffix}`.slice(0, 30),
    email: `e2e-${suffix}@example.com`,
    password: 'correct horse battery staple',
  }
}

export interface TestUser {
  name: string
  username: string
  email: string
  password: string
}

/** Fills and submits the registration form; leaves the page on `/login`
 * (registration never logs the user in — spec §7.1). */
export async function registerViaUi(page: Page, user: TestUser) {
  await page.goto('/register')
  await page.getByLabel('Name', { exact: true }).fill(user.name)
  await page.getByLabel('Username').fill(user.username)
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(user.password)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
}

/** Fills and submits the login form from wherever `page` currently is
 * (navigates to `/login` first unless already there) and waits for the
 * authenticated home screen. */
export async function loginViaUi(page: Page, user: Pick<TestUser, 'email' | 'password'>) {
  if (!page.url().endsWith('/login')) {
    await page.goto('/login')
  }
  const emailInput = page.getByLabel('Email')
  if ((await emailInput.inputValue()) !== user.email) {
    await emailInput.fill(user.email)
  }
  await page.getByLabel('Password').fill(user.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByRole('heading', { name: 'Twitter Smart Clone' })).toBeVisible()
}

export async function expectAuthenticated(page: Page, username: string) {
  await expect(page.getByRole('heading', { name: 'Twitter Smart Clone' })).toBeVisible()
  await expect(page.getByText(`Signed in as @${username}`)).toBeVisible()
}

export async function expectOnLoginScreen(page: Page) {
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
}

/** Known-benign console noise that isn't a real defect and would otherwise
 * make every run flaky/red:
 *
 * - Chromium's devtools protocol logs a `console.error` for *every*
 *   non-2xx `fetch`/XHR response (`"Failed to load resource: the server
 *   responded with a status of ..."`), regardless of whether the app
 *   handles it gracefully. Several flows below intentionally trigger 401s
 *   (invalid credentials, expired-token recovery, revoked-refresh reuse
 *   detection) and a 409 (duplicate registration) -- those are the
 *   behavior under test, not a defect, and are asserted on explicitly via
 *   the UI (toasts, redirects) in each test. A real app-level bug would
 *   still surface as a `pageerror` (uncaught exception/unhandled
 *   rejection) or an unexpected UI state, both of which this fixture still
 *   fails on.
 */
const ALLOWED_CONSOLE_PATTERNS: RegExp[] = [
  /^Failed to load resource: the server responded with a status of (401|409|429)/,
]

/**
 * Extends the base Playwright `test` with automatic assertions applied to
 * every test in this suite (acceptance criterion: "no browser console
 * error, unhandled request, secret disclosure... remains"):
 *
 * - Fails the test if the page logs a `console.error` or an uncaught
 *   `pageerror`.
 * - Fails the test if any request errors at the network level (DNS/connection
 *   failures) — this is distinct from a "real" non-2xx HTTP response (401s,
 *   409s, 429s are expected, legitimate parts of several flows below and are
 *   not requestfailed events).
 * - Fails the test if the access token or refresh token ever leaks into
 *   `localStorage`, `sessionStorage`, or a JS-readable cookie.
 */
export const test = base.extend<Record<string, never>>({
  page: async ({ page }, use) => {
    const consoleErrors: string[] = []
    const pageErrors: string[] = []
    const failedRequests: string[] = []

    page.on('console', (msg) => {
      if (msg.type() !== 'error') return
      const text = msg.text()
      if (ALLOWED_CONSOLE_PATTERNS.some((pattern) => pattern.test(text))) return
      consoleErrors.push(text)
    })
    page.on('pageerror', (error) => {
      pageErrors.push(error.message)
    })
    page.on('requestfailed', (request) => {
      // `net::ERR_ABORTED` is a benign Chromium quirk, not a real network
      // failure: it can fire *after* a response was already delivered (e.g.
      // a 204 with no body) when the page's document/frame lifecycle
      // changes immediately afterwards (a client-side redirect following a
      // successful logout, in this suite) -- the app already got its
      // response and acted on it correctly. Genuine connectivity failures
      // (refused/reset/DNS/timeout) use other `net::ERR_*` codes and still
      // fail the test.
      if (request.failure()?.errorText === 'net::ERR_ABORTED') return
      failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`)
    })

    await use(page)

    expect(consoleErrors, 'unexpected browser console error(s)').toEqual([])
    expect(pageErrors, 'unexpected uncaught page error(s)').toEqual([])
    expect(failedRequests, 'unexpected failed/unhandled request(s)').toEqual([])

    const storageSnapshot = await page.evaluate(() => ({
      localStorage: { ...localStorage },
      sessionStorage: { ...sessionStorage },
      cookie: document.cookie,
    }))
    const serialized = JSON.stringify(storageSnapshot).toLowerCase()
    // The access token must never be persisted; the refresh cookie must never
    // be JS-readable (httpOnly), so `document.cookie` must never contain it.
    expect(serialized, 'no auth token in localStorage/sessionStorage/document.cookie').not.toMatch(
      /access_token|refresh_token|bearer /,
    )
  },
})

export { expect }
