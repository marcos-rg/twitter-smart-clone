import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for the auth E2E suite (`TSC-AUTH-003`). Unlike
 * `playwright.config.ts` (which builds a static bundle and previews it with
 * no backend), this suite exercises the *real* containerized stack — the
 * `frontend` dev-server container talking to the `backend` container, which
 * talks to real PostgreSQL and Redis (spec: "verify... in the container
 * stack").
 *
 * There is deliberately no `webServer` entry here: the stack must already be
 * running (`make up`, or the `auth-e2e` CI job's `docker compose up -d`)
 * before this config is invoked, since it targets long-lived containers, not
 * a process this config should own the lifecycle of.
 *
 * `workers: 1` + `fullyParallel: false` keep every test serialized: the auth
 * endpoints share a single per-IP rate-limit bucket and several tests
 * (revoked-refresh-token reuse detection) depend on cookie/browser-context
 * state from a single logical session, so parallel workers would either trip
 * the rate limiter or race each other. `retries: 0` always (even in CI) so a
 * flaky pass can never hide behind a retry (acceptance criterion: "no...
 * flaky retry remains").
 */
export default defineConfig({
  testDir: './e2e-auth',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['html', { outputFolder: 'playwright-report/auth-e2e', open: 'never' }]],
  outputDir: 'test-results/auth-e2e',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
