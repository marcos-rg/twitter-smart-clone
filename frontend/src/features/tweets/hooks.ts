import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import * as tweetsApi from '../../api/tweets'
import * as likesApi from '../../api/likes'
import { ApiError } from '../../api/client'
import type { TweetCreateRequest, TweetListResponse, TweetView } from '../../api/types'

/** Human-readable message for any thrown error (mirrors
 * `features/users/hooks.describeUsersError`). */
export function describeTweetsError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Check your connection and try again.'
}

export function tweetQueryKey(id: string | undefined) {
  return ['tweet', id] as const
}

export function repliesQueryKey(id: string | undefined) {
  return ['tweet-replies', id] as const
}

export function userTweetsQueryKey(username: string | undefined) {
  return ['user-tweets', username?.toLowerCase()] as const
}

export function feedQueryKey() {
  return ['feed'] as const
}

const FEED_PAGE_SIZE = 20

/** The signed-in caller's home feed (TSC-FEED-002): own tweets + tweets from
 * everyone they follow, newest first, cursor-paginated. */
export function useFeed() {
  return useInfiniteQuery({
    queryKey: feedQueryKey(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      tweetsApi.getFeed({ cursor: pageParam, limit: FEED_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
  })
}

/**
 * Manual "refresh" for the feed (approved refresh semantics, TSC-FEED-002
 * human review): fetches a single fresh first page directly and replaces
 * the *entire* cached page list with it — the feed jumps back to the
 * newest tweets, matching mainstream "pull to refresh" behavior, rather
 * than re-fetching every previously-loaded page (which `useInfiniteQuery`'s
 * own `refetch()` would do, most-stale-first, for however many pages are
 * currently in memory).
 */
export function useRefreshFeed() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => tweetsApi.getFeed({ limit: FEED_PAGE_SIZE }),
    onSuccess: (page) => {
      queryClient.setQueryData<InfiniteData<TweetListResponse>>(feedQueryKey(), {
        pages: [page],
        pageParams: [undefined],
      })
    },
  })
}

/** A single tweet by id (tweet-detail page). */
export function useTweet(id: string | undefined) {
  return useQuery({
    queryKey: tweetQueryKey(id),
    queryFn: () => tweetsApi.getTweet(id as string),
    enabled: Boolean(id),
  })
}

const REPLIES_PAGE_SIZE = 20

/** Flat replies to a tweet, oldest first, cursor-paginated. */
export function useReplies(id: string | undefined) {
  return useInfiniteQuery({
    queryKey: repliesQueryKey(id),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      tweetsApi.listReplies(id as string, { cursor: pageParam, limit: REPLIES_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    enabled: Boolean(id),
  })
}

/** Prepends a freshly-created tweet to the first page of a cached
 * cursor-paginated `useInfiniteQuery` cache (a timeline or a replies list),
 * without touching the network. A no-op if that query has never been
 * fetched (nothing cached to prepend into). */
function prependToInfiniteCache(queryClient: QueryClient, key: QueryKey, tweet: TweetView) {
  queryClient.setQueryData<InfiniteData<TweetListResponse> | undefined>(key, (current) => {
    if (!current || current.pages.length === 0) return current
    const [firstPage, ...restPages] = current.pages
    return {
      ...current,
      pages: [{ ...firstPage, data: [tweet, ...firstPage.data] }, ...restPages],
    }
  })
}

export interface CreateTweetContext {
  /** When posting a root tweet from a profile screen, the profile whose
   * timeline cache should get the new tweet prepended (no refetch). Omit
   * when composing a reply — replies update the parent's replies cache
   * instead, based on the created tweet's own `parent_tweet_id`. */
  profileUsername?: string
  /** When posting a root tweet from the home feed, prepend it to the
   * cached feed (`['feed']`) too — the "newly-created-tweet" state
   * (TSC-FEED-002 acceptance criterion) with no forced refetch. */
  prependToFeed?: boolean
}

/**
 * Creates a tweet or (with `parent_tweet_id`) a flat reply, then updates
 * React Query caches directly from the response — no forced refetch
 * (acceptance criterion). On success:
 * - The new tweet is cached at its own `tweetQueryKey` (so navigating
 *   straight to `/tweet/{id}` next doesn't refetch).
 * - A reply is prepended to its parent's cached replies list, and the
 *   parent's own cached `TweetView` (if any) gets `reply_count` bumped by 1.
 * - A root tweet is prepended to `profileUsername`'s cached timeline, if
 *   provided.
 */
export function useCreateTweet(context: CreateTweetContext = {}) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: TweetCreateRequest) => tweetsApi.createTweet(payload),
    onSuccess: (tweet) => {
      queryClient.setQueryData(tweetQueryKey(tweet.id), tweet)

      if (tweet.parent_tweet_id) {
        prependToInfiniteCache(queryClient, repliesQueryKey(tweet.parent_tweet_id), tweet)
        queryClient.setQueryData<TweetView | undefined>(
          tweetQueryKey(tweet.parent_tweet_id),
          (current) => (current ? { ...current, reply_count: current.reply_count + 1 } : current),
        )
      } else {
        if (context.profileUsername) {
          prependToInfiniteCache(queryClient, userTweetsQueryKey(context.profileUsername), tweet)
        }
        if (context.prependToFeed) {
          prependToInfiniteCache(queryClient, feedQueryKey(), tweet)
        }
      }
    },
  })
}

/**
 * Cache plumbing for TSC-LIKE-002 ("like state/count updates consistently
 * across every cached representation of a tweet"). A single tweet can be
 * cached in an unbounded number of places at once — its own `tweetQueryKey`,
 * the home feed, any number of per-user timelines, and any number of
 * per-parent replies lists — and the set of usernames/parent ids currently
 * cached isn't known up front. So rather than enumerating query keys, these
 * helpers match every cached query *by key shape* (`'feed'` /
 * `'user-tweets'` / `'tweet-replies'` as the first key segment, matching
 * `feedQueryKey`/`userTweetsQueryKey`/`repliesQueryKey` above) and patch the
 * matching `TweetView` wherever it appears.
 */
const LIST_QUERY_KEY_PREFIXES = ['feed', 'user-tweets', 'tweet-replies'] as const

function isTweetListQueryKey(queryKey: QueryKey): boolean {
  return LIST_QUERY_KEY_PREFIXES.includes(queryKey[0] as (typeof LIST_QUERY_KEY_PREFIXES)[number])
}

function patchTweetInListResponse(
  data: TweetListResponse,
  id: string,
  patch: (tweet: TweetView) => TweetView,
): TweetListResponse {
  if (!data.data.some((tweet) => tweet.id === id)) return data
  return { ...data, data: data.data.map((tweet) => (tweet.id === id ? patch(tweet) : tweet)) }
}

function patchTweetInInfiniteData(
  data: InfiniteData<TweetListResponse>,
  id: string,
  patch: (tweet: TweetView) => TweetView,
): InfiniteData<TweetListResponse> {
  let changed = false
  const pages = data.pages.map((page) => {
    const next = patchTweetInListResponse(page, id, patch)
    if (next !== page) changed = true
    return next
  })
  return changed ? { ...data, pages } : data
}

/** One `{queryKey, data}` pair per cache entry that currently holds tweet
 * `id`, captured before an optimistic update so a failed mutation can
 * restore each one exactly (not just flip the flag back). */
export interface TweetCacheSnapshot {
  queryKey: QueryKey
  data: unknown
}

/** Every query whose data could contain tweet `id`: its own `tweetQueryKey`
 * plus every currently-cached feed/user-timeline/replies list. */
function tweetCacheQueries(queryClient: QueryClient, id: string) {
  return queryClient.getQueryCache().findAll({
    predicate: (query) =>
      (query.queryKey[0] === 'tweet' && query.queryKey[1] === id) ||
      isTweetListQueryKey(query.queryKey),
  })
}

export function snapshotTweetCaches(queryClient: QueryClient, id: string): TweetCacheSnapshot[] {
  return tweetCacheQueries(queryClient, id).map((query) => ({
    queryKey: query.queryKey,
    data: query.state.data,
  }))
}

export function restoreTweetCaches(queryClient: QueryClient, snapshots: TweetCacheSnapshot[]) {
  for (const { queryKey, data } of snapshots) {
    queryClient.setQueryData(queryKey, data)
  }
}

/** Applies `patch` to tweet `id` in every cache location that currently
 * holds it — the tweet-detail cache (a bare `TweetView`) and every
 * feed/timeline/replies cache (an `InfiniteData<TweetListResponse>`). A
 * no-op wherever the tweet isn't present. */
export function patchTweetEverywhere(
  queryClient: QueryClient,
  id: string,
  patch: (tweet: TweetView) => TweetView,
) {
  queryClient.setQueryData<TweetView | undefined>(tweetQueryKey(id), (current) =>
    current ? patch(current) : current,
  )
  for (const query of queryClient.getQueryCache().findAll({
    predicate: (q) => isTweetListQueryKey(q.queryKey),
  })) {
    queryClient.setQueryData<InfiniteData<TweetListResponse> | undefined>(
      query.queryKey,
      (current) => (current ? patchTweetInInfiniteData(current, id, patch) : current),
    )
  }
}

/**
 * Like/unlike a tweet with an optimistic update and full rollback on failure
 * (TSC-LIKE-002 acceptance criteria), mirroring
 * `useFollowMutation`/`useFollowMutation`'s shape but fanning the update out
 * to every cached representation of the tweet instead of a single profile
 * cache entry.
 *
 * `mutate(nextLiked)` flips `liked_by_viewer` and adjusts `like_count` by
 * exactly one (never below zero — `Math.max(0, …)` guards a doubled optimistic
 * decrement) immediately, before the network call resolves, everywhere the
 * tweet is currently cached. If the request fails, every touched cache entry
 * is restored to its exact pre-mutation snapshot — not just the flag — so a
 * failed like/unlike never leaves one cached view (say, the feed) out of sync
 * with another (say, the tweet-detail page). On success, the server's
 * authoritative `liked`/`like_count` replace the optimistic guess in every
 * cache location again, which matters for an idempotent repeat call (the
 * count doesn't move even though the optimistic update assumed it would) and
 * for a cache that had gone stale relative to another cached copy before the
 * click.
 *
 * Callers must not call `mutate` again while `isPending` is true —
 * `LikeButton` enforces this with a synchronous ref guard, the same pattern
 * `FollowButton` uses, since React state updates that back `isPending` are
 * not visible within the same synchronous click handler that fired the first
 * click (acceptance criterion: "rapid clicks cannot produce negative counts
 * or contradictory requests").
 */
export function useLikeMutation(tweetId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (nextLiked: boolean) =>
      nextLiked ? likesApi.likeTweet(tweetId) : likesApi.unlikeTweet(tweetId),
    onMutate: async (nextLiked: boolean) => {
      await queryClient.cancelQueries({
        predicate: (query) =>
          (query.queryKey[0] === 'tweet' && query.queryKey[1] === tweetId) ||
          isTweetListQueryKey(query.queryKey),
      })
      const snapshots = snapshotTweetCaches(queryClient, tweetId)
      patchTweetEverywhere(queryClient, tweetId, (tweet) =>
        tweet.liked_by_viewer === nextLiked
          ? tweet
          : {
              ...tweet,
              liked_by_viewer: nextLiked,
              like_count: Math.max(0, tweet.like_count + (nextLiked ? 1 : -1)),
            },
      )
      return { snapshots }
    },
    onError: (_error, _nextLiked, context) => {
      if (context?.snapshots) restoreTweetCaches(queryClient, context.snapshots)
    },
    onSuccess: (result) => {
      patchTweetEverywhere(queryClient, tweetId, (tweet) => ({
        ...tweet,
        liked_by_viewer: result.liked,
        like_count: result.like_count,
      }))
    },
  })
}
