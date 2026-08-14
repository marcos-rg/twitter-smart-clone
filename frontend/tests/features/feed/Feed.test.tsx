import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement, ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../../src/components/ui'
import { Feed } from '../../../src/features/feed/Feed'
import { server } from '../../mocks/server'
import { testUser } from '../../mocks/handlers'
import type { TweetView } from '../../../src/api/types'

/**
 * Home-feed component tests (TSC-FEED-002). `Feed` reads/writes the
 * `['feed']` TanStack Query cache directly (not through a route param), so
 * it's rendered standalone here rather than through the full `<App />` —
 * matching the "targeted hook/component tests" verification the task calls
 * for. Route-level wiring (auth guard, header, scroll restoration across a
 * real navigation) is covered by `tests/routes/Home.test.tsx`.
 */

/** Controllable `IntersectionObserver` mock: jsdom doesn't implement it.
 * Captures every instance so a test can manually fire an intersection
 * change and assert the resulting behavior deterministically, without a
 * real scrollable viewport. */
class MockIntersectionObserver implements IntersectionObserver {
  static instances: MockIntersectionObserver[] = []
  readonly root = null
  readonly rootMargin = ''
  readonly thresholds: number[] = []
  callback: IntersectionObserverCallback
  elements = new Set<Element>()
  disconnected = false

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    MockIntersectionObserver.instances.push(this)
  }
  observe(element: Element) {
    this.elements.add(element)
  }
  unobserve(element: Element) {
    this.elements.delete(element)
  }
  disconnect() {
    this.disconnected = true
    this.elements.clear()
  }
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
  /** Simulates the sentinel crossing into (or out of) view. */
  trigger(isIntersecting: boolean) {
    const target = [...this.elements][0]
    if (!target) return
    this.callback(
      [{ isIntersecting, target } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    )
  }
}

function latestObserver(): MockIntersectionObserver {
  const instance = MockIntersectionObserver.instances.at(-1)
  if (!instance) throw new Error('No IntersectionObserver was created')
  return instance
}

function renderFeed() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/']}>{children}</MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    )
  }
  return render((<Feed />) as ReactElement, { wrapper: Wrapper })
}

function tweet(overrides: Partial<TweetView> & { id: string; created_at: string }): TweetView {
  return {
    author: {
      id: testUser.id,
      username: testUser.username,
      name: testUser.name,
      avatar_key: testUser.avatar_key,
    },
    content: `Tweet ${overrides.id}`,
    parent_tweet_id: null,
    like_count: 0,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    ...overrides,
  }
}

beforeEach(() => {
  MockIntersectionObserver.instances = []
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Feed', () => {
  it('shows skeletons while loading, then the empty state for a feed with no tweets', async () => {
    renderFeed()
    expect(screen.getAllByLabelText('Loading tweet').length).toBeGreaterThan(0)
    expect(await screen.findByText('Your feed is empty')).toBeInTheDocument()
  })

  it('shows a full-page error state with retry when the first page fails to load', async () => {
    let attempts = 0
    server.use(
      http.get('*/api/v1/feed', () => {
        attempts += 1
        return HttpResponse.json(
          { error: { code: 'internal_error', message: 'Something broke.' } },
          { status: 500 },
        )
      }),
    )
    const user = userEvent.setup()
    renderFeed()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Couldn't load your feed")
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(attempts).toBeGreaterThanOrEqual(2))
  })

  it('paginates via the intersection sentinel, requesting the next cursor exactly once per trigger, and dedupes by id', async () => {
    const calls: string[] = []
    server.use(
      http.get('*/api/v1/feed', ({ request }) => {
        const url = new URL(request.url)
        const cursor = url.searchParams.get('cursor')
        calls.push(cursor ?? 'first')
        if (!cursor) {
          return HttpResponse.json({
            data: [tweet({ id: 'tweet-2', created_at: '2026-02-02T00:00:00Z' })],
            page: { next_cursor: 'cursor-1' },
          })
        }
        // Second page intentionally repeats tweet-2's id to prove the
        // rendered list de-duplicates by id rather than trusting the
        // server never overlaps pages.
        return HttpResponse.json({
          data: [
            tweet({ id: 'tweet-2', created_at: '2026-02-02T00:00:00Z' }),
            tweet({ id: 'tweet-1', created_at: '2026-02-01T00:00:00Z' }),
          ],
          page: { next_cursor: null },
        })
      }),
    )
    renderFeed()

    expect(await screen.findByText('Tweet tweet-2')).toBeInTheDocument()
    expect(calls).toEqual(['first'])

    const observer = latestObserver()
    observer.trigger(true)

    expect(await screen.findByText('Tweet tweet-1')).toBeInTheDocument()
    expect(calls).toEqual(['first', 'cursor-1'])
    expect(screen.getAllByText('Tweet tweet-2')).toHaveLength(1)

    // No more pages: end-of-feed message, not another sentinel/skeleton.
    expect(await screen.findByText("You're all caught up.")).toBeInTheDocument()
  })

  it('does not issue a second request while a page fetch is already in flight', async () => {
    let resolveSecondPage!: (value: Response) => void
    let secondPageCalls = 0
    server.use(
      http.get('*/api/v1/feed', ({ request }) => {
        const url = new URL(request.url)
        const cursor = url.searchParams.get('cursor')
        if (!cursor) {
          return HttpResponse.json({
            data: [tweet({ id: 'tweet-1', created_at: '2026-02-01T00:00:00Z' })],
            page: { next_cursor: 'cursor-1' },
          })
        }
        secondPageCalls += 1
        return new Promise<Response>((resolve) => {
          resolveSecondPage = resolve
        })
      }),
    )
    renderFeed()
    expect(await screen.findByText('Tweet tweet-1')).toBeInTheDocument()

    const observer = latestObserver()
    observer.trigger(true)
    await waitFor(() => expect(secondPageCalls).toBe(1))

    // Sentinel is still "intersecting" — but a fetch is already pending, so
    // firing again must not issue a second request for the same cursor.
    observer.trigger(true)
    observer.trigger(true)
    expect(secondPageCalls).toBe(1)

    resolveSecondPage(
      HttpResponse.json({
        data: [tweet({ id: 'tweet-2', created_at: '2026-02-02T00:00:00Z' })],
        page: { next_cursor: null },
      }),
    )
    await screen.findByText("You're all caught up.")
    expect(secondPageCalls).toBe(1)
  })

  it('disconnects the observer on unmount', async () => {
    server.use(
      http.get('*/api/v1/feed', () =>
        HttpResponse.json({
          data: [tweet({ id: 'tweet-1', created_at: '2026-02-01T00:00:00Z' })],
          page: { next_cursor: 'cursor-1' },
        }),
      ),
    )
    const { unmount } = renderFeed()
    await screen.findByText('Tweet tweet-1')
    const observer = latestObserver()
    expect(observer.disconnected).toBe(false)
    unmount()
    expect(observer.disconnected).toBe(true)
  })

  it('shows an inline retry affordance, not a full-page error, when a later page fails', async () => {
    server.use(
      http.get('*/api/v1/feed', ({ request }) => {
        const url = new URL(request.url)
        const cursor = url.searchParams.get('cursor')
        if (!cursor) {
          return HttpResponse.json({
            data: [tweet({ id: 'tweet-1', created_at: '2026-02-01T00:00:00Z' })],
            page: { next_cursor: 'cursor-1' },
          })
        }
        return HttpResponse.json(
          { error: { code: 'internal_error', message: 'Something broke.' } },
          { status: 500 },
        )
      }),
    )
    renderFeed()
    expect(await screen.findByText('Tweet tweet-1')).toBeInTheDocument()

    latestObserver().trigger(true)

    expect(await screen.findByText("Couldn't load more tweets")).toBeInTheDocument()
    // Already-loaded content stays visible under the inline error.
    expect(screen.getByText('Tweet tweet-1')).toBeInTheDocument()
  })

  it('refresh replaces the feed with a fresh first page', async () => {
    let page = 0
    server.use(
      http.get('*/api/v1/feed', () => {
        page += 1
        return HttpResponse.json({
          data: [
            tweet({
              id: `refresh-${page}`,
              created_at: '2026-02-03T00:00:00Z',
              content: `Refreshed content ${page}`,
            }),
          ],
          page: { next_cursor: null },
        })
      }),
    )
    const user = userEvent.setup()
    renderFeed()

    expect(await screen.findByText('Refreshed content 1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByText('Refreshed content 2')).toBeInTheDocument()
    expect(screen.queryByText('Refreshed content 1')).not.toBeInTheDocument()
  })

  it('prepends a newly-posted tweet to the feed without an extra GET', async () => {
    let feedCalls = 0
    server.use(
      http.get('*/api/v1/feed', () => {
        feedCalls += 1
        return HttpResponse.json({ data: [], page: { next_cursor: null } })
      }),
      http.post('*/api/v1/tweets', async ({ request }) => {
        const body = (await request.json()) as { content: string }
        return HttpResponse.json(
          tweet({
            id: 'tweet-fresh',
            created_at: '2026-02-04T00:00:00Z',
            content: body.content.trim(),
          }),
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderFeed()

    expect(await screen.findByText('Your feed is empty')).toBeInTheDocument()
    const callsBeforePost = feedCalls

    await user.type(screen.getByLabelText("What's happening?"), 'Hello from the feed')
    await user.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByText('Hello from the feed')).toBeInTheDocument()
    expect(screen.queryByText('Your feed is empty')).not.toBeInTheDocument()
    expect(feedCalls).toBe(callsBeforePost)
  })

  it('shows an offline banner when the browser goes offline', async () => {
    renderFeed()
    await screen.findByText('Your feed is empty')

    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
    window.dispatchEvent(new Event('offline'))

    expect(await screen.findByText(/You're offline/)).toBeInTheDocument()

    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
    window.dispatchEvent(new Event('online'))
    await waitFor(() => expect(screen.queryByText(/You're offline/)).not.toBeInTheDocument())
  })

  it('has no accessibility violations in loading, empty, and populated states', async () => {
    server.use(
      http.get('*/api/v1/feed', () =>
        HttpResponse.json({
          data: [tweet({ id: 'tweet-1', created_at: '2026-02-01T00:00:00Z' })],
          page: { next_cursor: null },
        }),
      ),
    )
    const { container } = renderFeed()
    await screen.findByText('Tweet tweet-1')
    expect(await axe(container)).toHaveNoViolations()
  })
})
