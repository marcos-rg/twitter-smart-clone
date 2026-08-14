import { test, expect, type Page } from '@playwright/test'

/**
 * Visual + responsive evidence for the profile, profile-edit, and search
 * screens (TSC-USER-002 verification: "attach profile/search screenshots at
 * required breakpoints" + "pages pass... three-breakpoint overflow checks").
 *
 * Like `e2e/auth.spec.ts` and `e2e/lab.spec.ts`, this project has no backend
 * (see `playwright.config.ts`) — `page.route` intercepts the auth bootstrap
 * and `/users/*` calls with fixture data so these routes render their real,
 * populated UI instead of an empty/error state. Full-stack behavior against
 * the real API is covered by `TSC-USER-003`'s Playwright suite.
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
  bio: 'Mathematician and writer. Building the analytical engine.',
  avatar_key: null,
  created_at: '2025-03-01T00:00:00Z',
}

const TWEETS = [
  {
    id: 'tweet-1',
    author_id: PROFILE.id,
    content: 'Just published a new paper on computational methods.',
    parent_tweet_id: null,
    like_count: 12,
    reply_count: 3,
    created_at: '2026-01-15T10:00:00Z',
  },
  {
    id: 'tweet-2',
    author_id: PROFILE.id,
    content: 'Working through a long chain of mechanical calculation today — notes to follow.',
    parent_tweet_id: null,
    like_count: 4,
    reply_count: 1,
    created_at: '2026-01-10T09:00:00Z',
  },
]

const SEARCH_RESULTS = [
  {
    id: 'user-2',
    name: 'Charles Babbage',
    username: 'babbage',
    bio: 'Inventor.',
    avatar_key: null,
  },
  { id: 'user-3', name: 'Alan Turing', username: 'turing', bio: 'Codebreaker.', avatar_key: null },
]

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
  await page.route('**/api/v1/users/ada/tweets*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: TWEETS, page: { next_cursor: null } }),
    }),
  )
  await page.route('**/api/v1/users/ada', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PROFILE) }),
  )
  await page.route('**/api/v1/users/search*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: SEARCH_RESULTS, page: { next_cursor: null } }),
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
  test(`profile screen renders at ${bp.name} width (${bp.width}px) without horizontal overflow`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/profile/ada')

    await expect(page.getByRole('heading', { name: 'Ada Lovelace' })).toBeVisible()
    await expect(
      page.getByText('Just published a new paper on computational methods.'),
    ).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/profile-${bp.name}.png`,
      fullPage: true,
    })
  })

  test(`profile-edit screen renders at ${bp.name} width (${bp.width}px) without horizontal overflow`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/profile/ada/edit')

    await expect(page.getByRole('heading', { name: 'Edit profile' })).toBeVisible()
    await expect(page.getByLabel('Username')).toHaveValue('ada')
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/profile-edit-${bp.name}.png`,
      fullPage: true,
    })
  })

  test(`search screen renders at ${bp.name} width (${bp.width}px) without horizontal overflow`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/search')

    await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
    await page.getByLabel('Search people').fill('babbage')
    await expect(page.getByText('Charles Babbage')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/search-${bp.name}.png`,
      fullPage: true,
    })
  })
}
