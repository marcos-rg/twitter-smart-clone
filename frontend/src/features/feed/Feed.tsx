import { useMemo, useState } from 'react'
import { Button, EmptyState, ErrorState } from '../../components/ui'
import { RefreshIcon } from '../../components/ui/icons'
import { TweetCard, TweetCardSkeleton } from '../../components/tweet/TweetCard'
import { TweetComposer } from '../tweets/TweetComposer'
import { describeTweetsError, useFeed, useRefreshFeed } from '../tweets/hooks'
import { useInfiniteScrollTrigger } from '../../lib/useInfiniteScrollTrigger'
import { useOnlineStatus } from '../../lib/useOnlineStatus'
import { useScrollRestoration } from '../../lib/useScrollRestoration'
import type { TweetView } from '../../api/types'

/** De-duplicates tweets by id, keeping the first occurrence — a defensive
 * acceptance criterion ("items are de-duplicated by ID"): the backend's
 * keyset pagination never repeats a row within one request, but a manual
 * refresh followed by paging forward again could otherwise surface the same
 * tweet twice across the merged cache. */
function dedupeById(tweets: TweetView[]): TweetView[] {
  const seen = new Set<string>()
  const result: TweetView[] = []
  for (const tweet of tweets) {
    if (seen.has(tweet.id)) continue
    seen.add(tweet.id)
    result.push(tweet)
  }
  return result
}

/**
 * Authenticated home feed (TSC-FEED-002): chronological, infinite-scrolling
 * timeline of the caller's own tweets plus tweets from everyone they
 * follow (`GET /api/v1/feed`, TSC-FEED-001).
 *
 * States covered (acceptance criteria):
 * - **Loading:** skeleton cards while the first page is in flight.
 * - **Retry:** a full-page `ErrorState` when the first page fails; a
 *   smaller inline retry affordance when a *later* page fails (the already-
 *   loaded tweets stay on screen either way).
 * - **Empty:** friendly empty state when the feed has no tweets at all.
 * - **End-of-feed:** a quiet "you're all caught up" message once
 *   `hasNextPage` is `false`.
 * - **Refresh:** `useRefreshFeed` — see its own docstring for the approved
 *   semantics (jump back to a fresh first page).
 * - **Newly-created-tweet:** the composer prepends straight into the feed
 *   cache (`prependToFeed`) with no forced refetch.
 * - **Offline:** a banner from `useOnlineStatus`, independent of query
 *   error state, since "no network" isn't the same failure as "server
 *   error".
 */
export function Feed() {
  const feed = useFeed()
  const refresh = useRefreshFeed()
  const isOnline = useOnlineStatus()
  const [nextPageFailed, setNextPageFailed] = useState(false)

  const items = useMemo(
    () => dedupeById(feed.data?.pages.flatMap((page) => page.data) ?? []),
    [feed.data],
  )

  const hasNextPage = feed.hasNextPage ?? false

  function handleLoadMore() {
    setNextPageFailed(false)
    // `fetchNextPage()` resolves (rather than rejects) even when the fetch
    // itself failed — TanStack Query surfaces that via the resolved
    // result's `isError`, not a rejected promise — so the failure has to be
    // read off the result, not caught.
    void feed.fetchNextPage().then((result) => {
      if (result.isError) setNextPageFailed(true)
    })
  }

  const sentinelRef = useInfiniteScrollTrigger({
    hasNextPage: hasNextPage && !nextPageFailed,
    isFetchingNextPage: feed.isFetchingNextPage,
    onLoadMore: handleLoadMore,
  })

  // Restore scroll position only once the feed actually has content to
  // scroll to (not while the first page is still loading).
  useScrollRestoration('home-feed', { ready: !feed.isLoading })

  return (
    <div>
      {!isOnline ? (
        <div
          role="status"
          className="border-b border-border bg-surface-hover px-4 py-2 text-center text-sm text-muted"
        >
          You&apos;re offline. Showing what&apos;s already loaded.
        </div>
      ) : null}

      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-base font-extrabold tracking-tight">Home</h2>
        <Button
          variant="ghost"
          size="sm"
          loading={refresh.isPending}
          onClick={() => refresh.mutate()}
        >
          <RefreshIcon className="size-4" />
          Refresh
        </Button>
      </div>

      <TweetComposer prependToFeed placeholder="What's happening?" />

      {feed.isLoading ? (
        <>
          <TweetCardSkeleton />
          <TweetCardSkeleton />
          <TweetCardSkeleton />
        </>
      ) : feed.isError && items.length === 0 ? (
        <div className="p-4">
          <ErrorState
            title="Couldn't load your feed"
            description={describeTweetsError(feed.error)}
            onRetry={() => void feed.refetch()}
          />
        </div>
      ) : items.length === 0 ? (
        <div className="p-4">
          <EmptyState
            title="Your feed is empty"
            description="Follow people to see their tweets here, or post your own."
          />
        </div>
      ) : (
        <>
          {items.map((tweet) => (
            <TweetCard key={tweet.id} tweet={tweet} />
          ))}

          {nextPageFailed ? (
            <div className="p-4">
              <ErrorState
                title="Couldn't load more tweets"
                description="Check your connection and try again."
                onRetry={handleLoadMore}
              />
            </div>
          ) : hasNextPage ? (
            <>
              <div ref={sentinelRef} aria-hidden="true" className="h-px" />
              {feed.isFetchingNextPage ? <TweetCardSkeleton /> : null}
            </>
          ) : (
            <p className="p-6 text-center text-sm text-muted">You&apos;re all caught up.</p>
          )}
        </>
      )}
    </div>
  )
}
