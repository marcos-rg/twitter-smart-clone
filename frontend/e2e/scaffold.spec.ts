import { test, expect } from '@playwright/test'

test('scaffold placeholder page renders', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: /twitter smart clone/i })).toBeVisible()
})
