import { test, expect, type Page } from '@playwright/test'

/**
 * Visual + responsive evidence for the tweet composer, card (with an
 * image), and detail/reply screens (TSC-TWEET-002 verification:
 * "screenshots for composer, card, detail, reply, and profile timeline at
 * required breakpoints"). Same no-backend, `page.route`-fixture pattern as
 * `e2e/profile-search.spec.ts` (see that file's header comment).
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

const ROOT_TWEET = {
  id: 'tweet-root',
  author: AUTHOR,
  content: 'A tweet with an attached image — see the gallery layout below.',
  parent_tweet_id: null,
  like_count: 12,
  reply_count: 2,
  liked_by_viewer: false,
  media: [{ key: 'tweet_image/user-1/photo.png', content_type: 'image/png', position: 0 }],
  links: [],
  created_at: '2026-01-15T10:00:00Z',
}

const REPLY_AUTHOR = {
  id: 'user-2',
  username: 'babbage',
  name: 'Charles Babbage',
  avatar_key: null,
}

const REPLIES = [
  {
    id: 'reply-1',
    author: REPLY_AUTHOR,
    content: 'Fascinating — how does it handle carry propagation?',
    parent_tweet_id: ROOT_TWEET.id,
    like_count: 1,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: '2026-01-15T11:00:00Z',
  },
  {
    id: 'reply-2',
    author: { id: 'user-3', username: 'turing', name: 'Alan Turing', avatar_key: null },
    content: 'See https://example.com/notes for the full write-up.',
    parent_tweet_id: ROOT_TWEET.id,
    like_count: 0,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [{ url: 'https://example.com/notes', start: 4, end: 30 }],
    created_at: '2026-01-15T12:00:00Z',
  },
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
      body: JSON.stringify({ data: [ROOT_TWEET], page: { next_cursor: null } }),
    }),
  )
  await page.route('**/api/v1/users/ada', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PROFILE) }),
  )
  await page.route(`**/api/v1/tweets/${ROOT_TWEET.id}/replies*`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: REPLIES, page: { next_cursor: null } }),
    }),
  )
  await page.route(`**/api/v1/tweets/${ROOT_TWEET.id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ROOT_TWEET),
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
  test(`own profile shows the composer and a tweet card with an image at ${bp.name} width (${bp.width}px)`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto('/profile/ada')

    await expect(page.getByLabel("What's happening?")).toBeVisible()
    await expect(page.getByText('A tweet with an attached image')).toBeVisible()
    await expect(page.locator('img[alt="Tweet image 1"]')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/tweet-composer-card-${bp.name}.png`,
      fullPage: true,
    })
  })

  test(`tweet detail page shows the reply composer and flat replies at ${bp.name} width (${bp.width}px)`, async ({
    page,
  }) => {
    await mockAuthenticatedApi(page)
    await page.setViewportSize({ width: bp.width, height: bp.height })
    await page.goto(`/tweet/${ROOT_TWEET.id}`)

    await expect(page.getByText('A tweet with an attached image')).toBeVisible()
    await expect(page.getByLabel('Post your reply')).toBeVisible()
    await expect(page.getByText('Fascinating — how does it handle carry propagation?')).toBeVisible()
    await expect(page.getByRole('link', { name: 'https://example.com/notes' })).toBeVisible()
    await expectNoHorizontalOverflow(page)

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expectNoHorizontalOverflow(page)

    await page.screenshot({
      path: `test-results/screenshots/tweet-detail-reply-${bp.name}.png`,
      fullPage: true,
    })
  })
}
