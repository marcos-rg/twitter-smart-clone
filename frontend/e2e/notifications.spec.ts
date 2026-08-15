import { test, expect, type Page } from '@playwright/test'

/**
 * Visual + responsive evidence for the notifications panel and unread nav
 * badge (TSC-NOTIF-002 verification: "attach responsive screenshots"). Same
 * no-backend, `page.route`-fixture pattern as `e2e/likes.spec.ts` and
 * `e2e/feed.spec.ts` (see those files' header comments) — the live
 * WebSocket connection itself isn't exercised here (that's covered by the
 * backend's own `tests/test_ws.py`, per `docs/websocket-realtime.md`); this
 * suite only proves out the REST-backed panel/badge UI at each breakpoint.
 */

const breakpoints = [
  { name: 'mobile', width: 375, height: 812 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
] as const

const PROFILE = {
  id: 'user-1',
  name: 'Ada Lovelace',
  username: 'ada',
  bio: 'Mathematician and writer.',
  avatar_key: null,
  created_at: '2025-03-01T00:00:00Z',
  followers_count: 5,
  following_count: 2,
  is_following: false,
}

const ACTOR = {
  id: 'user-2',
  username: 'grace',
  name: 'Grace Hopper',
  avatar_key: null,
}

function notificationItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 'notif-1',
    type: 'like',
    actor: ACTOR,
    tweet_id: 'tweet-1',
    is_read: false,
    created_at: '2026-08-14T09:00:00Z',
    ...overrides,
  }
}

async function mockAuthenticatedApi(page: Page) {
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'fixture-token',
        token_type: 'bearer',
        expires_in: 900,
      }),
    }),
  )
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...PROFILE, email: 'ada@example.com' }),
    }),
  )
  await page.route('**/api/v1/feed*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [], page: { next_cursor: null } }),
    }),
  )
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    return doc.scrollWidth - doc.clientWidth
  })
  expect(overflow).toBeLessThanOrEqual(0)
}

for (const bp of breakpoints) {
  test(`populated notifications panel with an unread nav badge renders overflow-free at ${bp.name} width (${bp.width}px)`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.route('**/api/v1/notifications*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: [
            notificationItem({ id: 'n-follow', type: 'follow', tweet_id: null }),
            notificationItem({ id: 'n-like', type: 'like' }),
            notificationItem({ id: 'n-reply', type: 'reply', is_read: true }),
          ],
          page: { next_cursor: null },
          unread_count: 2,
        }),
      }),
    )
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/notifications')

    await expect(page.getByText('2 unread notifications')).toBeVisible()
    await expect(page.getByText('Grace Hopper followed you')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/notifications-populated-${bp.name}.png`,
      fullPage: true,
    })
  })

  test(`empty notifications panel renders overflow-free at ${bp.name} width (${bp.width}px)`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.route('**/api/v1/notifications*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [], page: { next_cursor: null }, unread_count: 0 }),
      }),
    )
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/notifications')

    await expect(page.getByText('No notifications yet')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/notifications-empty-${bp.name}.png`,
      fullPage: true,
    })
  })
}

test('"Mark all read" clears the unread nav badge without a page reload', async ({ page }) => {
  await mockAuthenticatedApi(page)
  await page.route('**/api/v1/notifications*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: [notificationItem({ id: 'a' }), notificationItem({ id: 'b' })],
        page: { next_cursor: null },
        unread_count: 2,
      }),
    }),
  )
  await page.route('**/api/v1/notifications/read', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ marked_read: 2, unread_count: 0 }),
    }),
  )
  await page.goto('/notifications')

  await expect(page.getByText('2 unread notifications')).toBeVisible()
  await expect(page.getByRole('link', { name: /notifications, 2 unread/i }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Mark all read' }).click()

  await expect(page.getByText('0 unread notifications')).toBeVisible()
  await expect(page.getByRole('link', { name: /notifications, \d+ unread/i })).toHaveCount(0)

  await page.screenshot({ path: 'test-results/screenshots/notifications-all-read.png' })
})
