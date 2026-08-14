import { test, expect, type Page } from '@playwright/test'

/**
 * Design lab responsive checks (TSC-UX-001): the lab must render at the
 * three product breakpoints (mobile <640px, tablet 640–1024px, desktop
 * >1024px) without horizontal overflow, and must respect
 * prefers-reduced-motion. Full-page screenshots are saved to
 * ../docs/design-system/screenshots/ as review evidence for the human gate.
 */
const breakpoints = [
  { name: 'mobile', width: 375, height: 812 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
] as const

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    return doc.scrollWidth - doc.clientWidth
  })
  expect(overflow).toBeLessThanOrEqual(0)
}

for (const bp of breakpoints) {
  test(`lab renders at ${bp.name} width (${bp.width}px) without horizontal overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/lab')

    await expect(page.getByRole('heading', { name: 'Design Lab' })).toBeVisible()
    await expectNoHorizontalOverflow(page)

    // Scroll through the whole page and re-check: content revealed later
    // (e.g. the long-content tweet) must not overflow either.
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `../docs/design-system/screenshots/lab-${bp.name}.png`,
      fullPage: true,
    })
  })
}

test('app shell renders at the three breakpoints without horizontal overflow', async ({ page }) => {
  for (const bp of breakpoints) {
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/')
    // "/" is a protected route (TSC-AUTH-002); without a session it redirects
    // to /login, rendered inside the same AppShell chrome.
    await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
    await expectNoHorizontalOverflow(page)
  }
})

test('motion is disabled when the user prefers reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/lab')

  const button = page.getByRole('button', { name: 'Primary' })
  const transitionDuration = await button.evaluate((el) => getComputedStyle(el).transitionDuration)
  // The global reduced-motion rule clamps all transitions to 0.01ms.
  expect(parseFloat(transitionDuration)).toBeLessThan(0.001)
})
