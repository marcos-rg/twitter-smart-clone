import { test, expect } from '@playwright/test'

test('unauthenticated visitors are redirected from "/" to the login screen', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
})
