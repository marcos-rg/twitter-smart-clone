import { test, expect } from '@playwright/test'

/**
 * Visual evidence for the auth screens at mobile and desktop breakpoints
 * (TSC-AUTH-002 verification: "attach mobile and desktop auth-screen
 * screenshots"). No backend is running for this e2e project, so these only
 * exercise rendering/layout, not live submission — functional coverage lives
 * in the Vitest/RTL/MSW suite.
 */

const MOBILE_VIEWPORT = { width: 390, height: 844 } // iPhone 12-ish
const DESKTOP_VIEWPORT = { width: 1440, height: 900 }

test.describe('Login screen', () => {
  test('renders correctly on mobile and desktop', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()

    await page.setViewportSize(MOBILE_VIEWPORT)
    await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/login-mobile.png' })

    await page.setViewportSize(DESKTOP_VIEWPORT)
    await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/login-desktop.png' })
  })
})

test.describe('Register screen', () => {
  test('renders correctly on mobile and desktop', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible()

    await page.setViewportSize(MOBILE_VIEWPORT)
    await expect(page.getByRole('button', { name: 'Create account' })).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/register-mobile.png' })

    await page.setViewportSize(DESKTOP_VIEWPORT)
    await expect(page.getByRole('button', { name: 'Create account' })).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/register-desktop.png' })
  })
})
