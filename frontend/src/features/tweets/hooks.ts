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
      } else if (context.profileUsername) {
        prependToInfiniteCache(queryClient, userTweetsQueryKey(context.profileUsername), tweet)
      }
    },
  })
}
