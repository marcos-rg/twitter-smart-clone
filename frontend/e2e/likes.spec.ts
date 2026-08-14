import { test, expect, type Page } from '@playwright/test'

/**
 * Visual evidence for the like/unlike control (TSC-LIKE-002 verification:
 * "component-lab captures for liked, unliked, pending, failed, and
 * reduced-motion states"). Same no-backend, `page.route`-fixture pattern as
 * `e2e/tweets.spec.ts` (see that file's header comment) — a single tweet on
 * the signed-in user's own profile, with the like endpoint mocked per
 * scenario.
 */

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

function tweet(overrides: Record<string, unknown> = {}) {
  return {
    id: 'tweet-like-demo',
    author: AUTHOR,
    content: 'A tweet worth liking.',
    parent_tweet_id: null,
    like_count: 8,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: '2026-01-15T10:00:00Z',
    ...overrides,
  }
}

async function mockAuthenticatedApi(page: Page, seedTweet: ReturnType<typeof tweet>) {
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
      body: JSON.stringify({ data: [seedTweet], page: { next_cursor: null } }),
    }),
  )
  await page.route('**/api/v1/users/ada', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PROFILE) }),
  )
}

test('unliked tweet renders an outline heart, unpressed', async ({ page }) => {
  await mockAuthenticatedApi(page, tweet({ liked_by_viewer: false, like_count: 8 }))
  await page.goto('/profile/ada')

  const likeButton = page.getByRole('button', { name: 'Like, 8 likes' })
  await expect(likeButton).toBeVisible()
  await expect(likeButton).toHaveAttribute('aria-pressed', 'false')

  await page.screenshot({ path: 'test-results/screenshots/like-unliked.png' })
})

test('liked tweet renders a filled heart, pressed', async ({ page }) => {
  await mockAuthenticatedApi(page, tweet({ liked_by_viewer: true, like_count: 9 }))
  await page.goto('/profile/ada')

  const likeButton = page.getByRole('button', { name: 'Liked, 9 likes' })
  await expect(likeButton).toBeVisible()
  await expect(likeButton).toHaveAttribute('aria-pressed', 'true')

  await page.screenshot({ path: 'test-results/screenshots/like-liked.png' })
})

test('a slow like request shows a disabled, pending button', async ({ page }) => {
  const seed = tweet({ liked_by_viewer: false, like_count: 8 })
  await mockAuthenticatedApi(page, seed)
  await page.route(`**/api/v1/tweets/${seed.id}/like`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ liked: true, like_count: 9 }),
    })
  })
  await page.goto('/profile/ada')

  const likeButton = page.getByRole('button', { name: 'Like, 8 likes' })
  await likeButton.click()

  // Optimistic update flips the label immediately; the button is disabled
  // while the (slow) request is still in flight.
  const pendingButton = page.getByRole('button', { name: 'Liked, 9 likes' })
  await expect(pendingButton).toBeVisible()
  await expect(pendingButton).toBeDisabled()

  await page.screenshot({ path: 'test-results/screenshots/like-pending.png' })
})

test('a failed like request rolls back and shows an accessible error toast', async ({ page }) => {
  const seed = tweet({ liked_by_viewer: false, like_count: 8 })
  await mockAuthenticatedApi(page, seed)
  await page.route(`**/api/v1/tweets/${seed.id}/like`, (route) =>
    route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'rate_limited', message: 'Too many requests.' } }),
    }),
  )
  await page.goto('/profile/ada')

  const likeButton = page.getByRole('button', { name: 'Like, 8 likes' })
  await likeButton.click()

  // Rolls back to the original unliked state and surfaces an accessible
  // (role="alert") error toast.
  await expect(page.getByRole('button', { name: 'Like, 8 likes' })).toBeVisible()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText("Couldn't like this tweet.")
  await expect(alert).toContainText('Too many requests.')

  await page.screenshot({ path: 'test-results/screenshots/like-failed.png' })
})

test('the like "pop" animation is disabled under prefers-reduced-motion', async ({ page }) => {
  const seed = tweet({ liked_by_viewer: false, like_count: 8 })
  await mockAuthenticatedApi(page, seed)
  await page.route(`**/api/v1/tweets/${seed.id}/like`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ liked: true, like_count: 9 }),
    }),
  )
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/profile/ada')

  const likeButton = page.getByRole('button', { name: 'Like, 8 likes' })
  await likeButton.click()

  const heartGlyph = page.getByRole('button', { name: 'Liked, 9 likes' }).locator('span').first()
  await expect(heartGlyph).toBeVisible()
  // The global reduced-motion rule (index.css) clamps every animation to
  // 0.01ms, and `LikeButton` additionally drops the `animate-like-pop`
  // class's underlying animation via `motion-reduce:animate-none`.
  const animationDuration = await heartGlyph.evaluate(
    (el) => getComputedStyle(el).animationDuration,
  )
  expect(parseFloat(animationDuration)).toBeLessThan(0.001)

  await page.screenshot({ path: 'test-results/screenshots/like-reduced-motion.png' })
})
