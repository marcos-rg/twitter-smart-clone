import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import {
  feedQueryKey,
  repliesQueryKey,
  tweetQueryKey,
  useLikeMutation,
  userTweetsQueryKey,
} from '../../../src/features/tweets/hooks'
import { server } from '../../mocks/server'
import type { TweetListResponse, TweetView } from '../../../src/api/types'

/**
 * Unit tests for `useLikeMutation`'s cache fan-out (TSC-LIKE-002). Exercised
 * directly against a `QueryClient` (no rendered UI) so every cache location
 * a tweet can live in — its own `tweetQueryKey`, the feed, a user timeline,
 * and a replies list — can be seeded and asserted precisely, including the
 * "one cache is stale relative to another" scenario that's awkward to force
 * through the UI. Button-level behavior (disabled/pending, toast, rapid
 * clicks, animation) is covered in
 * `tests/routes/LikeInteractions.test.tsx`.
 */

function makeTweet(overrides: Partial<TweetView> = {}): TweetView {
  return {
    id: 'tweet-1',
    author: { id: 'user-1', username: 'ada', name: 'Ada Lovelace', avatar_key: null },
    content: 'Hello world',
    parent_tweet_id: null,
    like_count: 4,
    reply_count: 0,
    liked_by_viewer: false,
    media: [],
    links: [],
    created_at: '2026-08-13T14:00:00Z',
    ...overrides,
  }
}

function listResponse(tweet: TweetView): TweetListResponse {
  return { data: [tweet], page: { next_cursor: null } }
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

/** Seeds every known cache shape (`tweetQueryKey`, `feedQueryKey`,
 * `userTweetsQueryKey`, `repliesQueryKey`) with the same tweet, so a single
 * mutation's fan-out across all of them can be asserted. */
function seedEveryCache(queryClient: QueryClient, tweet: TweetView) {
  queryClient.setQueryData(tweetQueryKey(tweet.id), tweet)
  queryClient.setQueryData(feedQueryKey(), {
    pages: [listResponse(tweet)],
    pageParams: [undefined],
  })
  queryClient.setQueryData(userTweetsQueryKey('ada'), {
    pages: [listResponse(tweet)],
    pageParams: [undefined],
  })
  queryClient.setQueryData(repliesQueryKey('parent-1'), {
    pages: [listResponse(tweet)],
    pageParams: [undefined],
  })
}

function readEveryCache(queryClient: QueryClient, id: string) {
  const tweet = queryClient.getQueryData<TweetView>(tweetQueryKey(id))
  const feedTweet = (
    queryClient.getQueryData(feedQueryKey()) as { pages: TweetListResponse[] } | undefined
  )?.pages[0]?.data.find((t) => t.id === id)
  const timelineTweet = (
    queryClient.getQueryData(userTweetsQueryKey('ada')) as
      { pages: TweetListResponse[] } | undefined
  )?.pages[0]?.data.find((t) => t.id === id)
  const replyTweet = (
    queryClient.getQueryData(repliesQueryKey('parent-1')) as
      { pages: TweetListResponse[] } | undefined
  )?.pages[0]?.data.find((t) => t.id === id)
  return { tweet, feedTweet, timelineTweet, replyTweet }
}

describe('useLikeMutation', () => {
  it('updates like state/count consistently across every cached representation on success', async () => {
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: true, like_count: 5 }),
      ),
    )
    const queryClient = makeClient()
    seedEveryCache(queryClient, makeTweet({ like_count: 4, liked_by_viewer: false }))
    const { result } = renderHook(() => useLikeMutation('tweet-1'), {
      wrapper: wrapper(queryClient),
    })

    act(() => result.current.mutate(true))

    // Optimistic: every cache flips before the network response resolves
    // (`onMutate` itself is async — it awaits `cancelQueries` first — so
    // this is observed via `waitFor` rather than immediately after
    // `mutate()` returns).
    await waitFor(() => {
      const optimistic = readEveryCache(queryClient, 'tweet-1')
      expect(optimistic.tweet?.liked_by_viewer).toBe(true)
      expect(optimistic.tweet?.like_count).toBe(5)
      expect(optimistic.feedTweet?.like_count).toBe(5)
      expect(optimistic.timelineTweet?.like_count).toBe(5)
      expect(optimistic.replyTweet?.like_count).toBe(5)
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const final = readEveryCache(queryClient, 'tweet-1')
    expect(final.tweet).toMatchObject({ liked_by_viewer: true, like_count: 5 })
    expect(final.feedTweet).toMatchObject({ liked_by_viewer: true, like_count: 5 })
    expect(final.timelineTweet).toMatchObject({ liked_by_viewer: true, like_count: 5 })
    expect(final.replyTweet).toMatchObject({ liked_by_viewer: true, like_count: 5 })
  })

  it('reconciles a stale cache to the server-authoritative count on success (idempotent repeat)', async () => {
    // The feed cache is stale (already liked, count 6) relative to the
    // tweet-detail cache (not-yet-liked, count 5) — e.g. a previous like
    // landed in the feed but the detail page was opened from an older
    // snapshot. A repeat "like" call is idempotent server-side (count
    // doesn't move), and every cache must converge on the same truth.
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: true, like_count: 6 }),
      ),
    )
    const queryClient = makeClient()
    queryClient.setQueryData(
      tweetQueryKey('tweet-1'),
      makeTweet({ like_count: 5, liked_by_viewer: false }),
    )
    queryClient.setQueryData(feedQueryKey(), {
      pages: [listResponse(makeTweet({ like_count: 6, liked_by_viewer: true }))],
      pageParams: [undefined],
    })
    const { result } = renderHook(() => useLikeMutation('tweet-1'), {
      wrapper: wrapper(queryClient),
    })

    act(() => result.current.mutate(true))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const final = readEveryCache(queryClient, 'tweet-1')
    expect(final.tweet).toMatchObject({ liked_by_viewer: true, like_count: 6 })
    expect(final.feedTweet).toMatchObject({ liked_by_viewer: true, like_count: 6 })
  })

  it('fully rolls back every cache to its exact pre-mutation snapshot on failure', async () => {
    server.use(
      http.post('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json(
          { error: { code: 'rate_limited', message: 'Too many requests.' } },
          { status: 429 },
        ),
      ),
    )
    const queryClient = makeClient()
    seedEveryCache(queryClient, makeTweet({ like_count: 4, liked_by_viewer: false }))
    const { result } = renderHook(() => useLikeMutation('tweet-1'), {
      wrapper: wrapper(queryClient),
    })

    act(() => result.current.mutate(true))
    await waitFor(() => expect(result.current.isError).toBe(true))

    const final = readEveryCache(queryClient, 'tweet-1')
    expect(final.tweet).toMatchObject({ liked_by_viewer: false, like_count: 4 })
    expect(final.feedTweet).toMatchObject({ liked_by_viewer: false, like_count: 4 })
    expect(final.timelineTweet).toMatchObject({ liked_by_viewer: false, like_count: 4 })
    expect(final.replyTweet).toMatchObject({ liked_by_viewer: false, like_count: 4 })
  })

  it('never drives a cached like_count below zero even if unlike is somehow retried', async () => {
    server.use(
      http.delete('*/api/v1/tweets/tweet-1/like', () =>
        HttpResponse.json({ liked: false, like_count: 0 }),
      ),
    )
    const queryClient = makeClient()
    // Already at zero — an optimistic decrement must clamp, not go negative.
    queryClient.setQueryData(
      tweetQueryKey('tweet-1'),
      makeTweet({ like_count: 0, liked_by_viewer: true }),
    )
    const { result } = renderHook(() => useLikeMutation('tweet-1'), {
      wrapper: wrapper(queryClient),
    })

    act(() => result.current.mutate(false))

    await waitFor(() => {
      const optimistic = queryClient.getQueryData<TweetView>(tweetQueryKey('tweet-1'))
      expect(optimistic?.like_count).toBe(0)
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })
})
