import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { ToastProvider } from '../../../src/components/ui'
import { TweetCard, TweetCardSkeleton } from '../../../src/components/tweet/TweetCard'
import type { TweetView } from '../../../src/api/types'

/** TweetCard component tests (TSC-TWEET-002/TSC-LIKE-002): safe rendering
 * (no `dangerouslySetInnerHTML`, no HTML injection from tweet content),
 * image gallery layout, avatar fallback, and navigation. `LikeButton`
 * interaction/optimistic-update behavior itself is covered separately in
 * `tests/routes/LikeInteractions.test.tsx`, against `<App />` + MSW, so its
 * cache fan-out can be exercised for real; this file only needs a
 * `QueryClientProvider`/`ToastProvider` present so `TweetCard` (which now
 * always renders a live `LikeButton`) doesn't throw. */

function makeTweet(overrides: Partial<TweetView> = {}): TweetView {
  return {
    id: 'tweet-1',
    author: { id: 'user-1', username: 'ada', name: 'Ada Lovelace', avatar_key: null },
    content: 'Hello world',
    parent_tweet_id: null,
    like_count: 4,
    reply_count: 2,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: '2026-08-13T14:00:00Z',
    ...overrides,
  }
}

function renderCard(tweet: TweetView, route = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="*" element={<TweetCard tweet={tweet} />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('TweetCard', () => {
  it('renders author, content, and accessible action counts', () => {
    renderCard(makeTweet())
    expect(screen.getByRole('article', { name: 'Tweet by Ada Lovelace' })).toBeInTheDocument()
    expect(screen.getByText('@ada')).toBeInTheDocument()
    expect(screen.getByText('Hello world')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reply, 2 replies' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Like, 4 likes' })).toBeInTheDocument()
    expect(screen.queryByLabelText(/repost/i)).not.toBeInTheDocument()
  })

  it('reflects liked_by_viewer as a pressed, filled-heart button', () => {
    renderCard(makeTweet({ liked_by_viewer: true, like_count: 10 }))
    const likeButton = screen.getByRole('button', { name: 'Liked, 10 likes' })
    expect(likeButton).toHaveAttribute('aria-pressed', 'true')
  })

  it('wraps long content instead of overflowing', () => {
    const longContent = 'verylongword'.repeat(100)
    renderCard(makeTweet({ content: longContent }))
    const paragraph = screen.getByText((_, element) => element?.tagName === 'P')
    expect(paragraph.className).toContain('break-words')
    expect(paragraph.className).toContain('whitespace-pre-wrap')
  })

  it('falls back to initials when there is no avatar', () => {
    renderCard(makeTweet())
    expect(screen.getByRole('img', { name: 'Ada Lovelace' })).toHaveTextContent('AL')
  })

  it('renders up to four images in the gallery, ordered by position', () => {
    renderCard(
      makeTweet({
        media: [
          { key: 'img-3', content_type: 'image/png', position: 2 },
          { key: 'img-1', content_type: 'image/png', position: 0 },
          { key: 'img-4', content_type: 'image/png', position: 3 },
          { key: 'img-2', content_type: 'image/png', position: 1 },
        ],
      }),
    )
    const images = screen
      .getAllByRole('img')
      .filter((img) => img.getAttribute('alt')?.startsWith('Tweet image'))
    expect(images).toHaveLength(4)
    expect(images.map((img) => img.getAttribute('alt'))).toEqual([
      'Tweet image 1',
      'Tweet image 2',
      'Tweet image 3',
      'Tweet image 4',
    ])
  })

  it('renders a real link only for server-provided link spans, with content as plain text otherwise', () => {
    const content = 'see https://example.com now'
    renderCard(
      makeTweet({
        content,
        links: [{ url: 'https://example.com', start: 4, end: 23 }],
      }),
    )
    const link = screen.getByRole('link', { name: 'https://example.com' })
    expect(link).toHaveAttribute('href', 'https://example.com')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('never turns malicious content into executable markup', () => {
    const content = '<img src=x onerror=alert(1)> javascript:alert(1) <script>alert(2)</script>'
    const { container } = renderCard(makeTweet({ content, links: [] }))

    // The raw tag text is shown as text, not parsed as HTML.
    expect(screen.getByText(content)).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
    // Only the avatar's own <img> exists — no injected <img> from content.
    expect(container.querySelectorAll('img')).toHaveLength(0)
  })

  it('navigates to the tweet detail route on card click', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/']}>
            <Routes>
              <Route path="/" element={<TweetCard tweet={makeTweet()} />} />
              <Route path="/tweet/:tweetId" element={<div>Tweet detail page</div>} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    await user.click(screen.getByRole('article', { name: 'Tweet by Ada Lovelace' }))
    expect(await screen.findByText('Tweet detail page')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderCard(makeTweet())
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders a labelled loading skeleton', () => {
    render(<TweetCardSkeleton />)
    expect(screen.getByRole('status', { name: 'Loading tweet' })).toBeInTheDocument()
  })
})
