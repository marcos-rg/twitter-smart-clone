import { test, expect, type Page } from '@playwright/test'

/**
 * Visual + responsive evidence for the home feed (TSC-FEED-002
 * verification: "responsive screenshots with multi-page seeded data").
 * Same no-backend, `page.route`-fixture pattern as `e2e/tweets.spec.ts` and
 * `e2e/profile-search.spec.ts` (see those files' header comments).
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

const AUTHOR = {
  id: PROFILE.id,
  username: PROFILE.username,
  name: PROFILE.name,
  avatar_key: PROFILE.avatar_key,
}

/** Two pages of seeded feed data (25 tweets total), so pagination via the
 * IntersectionObserver sentinel has real multi-page content to walk
 * through. */
const PAGE_SIZE = 20
const TOTAL_TWEETS = 25

function makeTweet(index: number) {
  return {
    id: `tweet-${index}`,
    author: AUTHOR,
    content: `Feed tweet number ${index} — chronological, newest first.`,
    parent_tweet_id: null,
    like_count: index,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: new Date(2026, 0, 1, 0, TOTAL_TWEETS - index).toISOString(),
  }
}

const ALL_TWEETS = Array.from({ length: TOTAL_TWEETS }, (_, i) => makeTweet(i + 1))

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
}

async function mockPaginatedFeed(page: Page) {
  await page.route('**/api/v1/feed*', (route) => {
    const url = new URL(route.request().url())
    const cursor = url.searchParams.get('cursor')
    const start = cursor ? Number(cursor) : 0
    const slice = ALL_TWEETS.slice(start, start + PAGE_SIZE)
    const nextIndex = start + PAGE_SIZE
    const nextCursor = nextIndex < ALL_TWEETS.length ? String(nextIndex) : null
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: slice, page: { next_cursor: nextCursor } }),
    })
  })
}

async function mockEmptyFeed(page: Page) {
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
  test(`home feed loads a second page on scroll and stays overflow-free at ${bp.name} width (${bp.width}px)`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await mockPaginatedFeed(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/')

    await expect(page.getByText('Feed tweet number 1 —')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/feed-first-page-${bp.name}.png`,
      fullPage: false,
    })

    // Scroll to the bottom to cross the IntersectionObserver sentinel and
    // pull in the second page.
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expect(page.getByText(`Feed tweet number ${TOTAL_TWEETS} —`)).toBeVisible()
    await expect(page.getByText("You're all caught up.")).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/feed-end-of-feed-${bp.name}.png`,
      fullPage: true,
    })
  })

  test(`home feed shows an empty state with no horizontal overflow at ${bp.name} width (${bp.width}px)`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await mockEmptyFeed(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/')

    await expect(page.getByText('Your feed is empty')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/feed-empty-${bp.name}.png`,
      fullPage: true,
    })
  })
}

test('refresh replaces the feed with a fresh first page without a full reload', async ({
  page,
}) => {
  await mockAuthenticatedApi(page)
  let refreshed = false
  await page.route('**/api/v1/feed*', (route) => {
    const url = new URL(route.request().url())
    if (url.searchParams.get('cursor')) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [ALL_TWEETS[1]], page: { next_cursor: null } }),
      })
      return
    }
    const tweet = refreshed ? ALL_TWEETS[0] : ALL_TWEETS[1]
    refreshed = true
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [tweet], page: { next_cursor: null } }),
    })
  })
  await page.goto('/')

  await expect(page.getByText('Feed tweet number 2 —')).toBeVisible()
  await page.getByRole('button', { name: 'Refresh' }).click()
  await expect(page.getByText('Feed tweet number 1 —')).toBeVisible()
})
