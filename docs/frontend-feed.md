# Responsive infinite-scrolling home feed (TSC-FEED-002)

Frontend slice on top of the home-feed backend (`GET /api/v1/feed`,
`TSC-FEED-001`, see [`feed-backend.md`](./feed-backend.md)): the
authenticated `/` route now renders a real chronological, infinite-scrolling
feed instead of the routing/auth-guard placeholder it shipped with. Reuses
`TweetCard`/`TweetComposer` from `TSC-TWEET-002` unchanged — a tweet in the
feed looks and behaves exactly like a tweet anywhere else in the app.

## API + data hooks

[`api/tweets.ts`](../frontend/src/api/tweets.ts) gained `getFeed` (`GET
/api/v1/feed`, same cursor/limit query params and `TweetListResponse` shape
as every other tweet-listing endpoint).

[`features/tweets/hooks.ts`](../frontend/src/features/tweets/hooks.ts):

- `useFeed()` — `useInfiniteQuery` keyed `['feed']`, 20 items/page, same
  `getNextPageParam` pattern as `useReplies`/`useUserTweets`.
- `useRefreshFeed()` — see "Refresh semantics" below.
- `useCreateTweet`'s `CreateTweetContext` gained `prependToFeed?: boolean`;
  `TweetComposer` gained the matching prop. Posting a root tweet from the
  feed (`<TweetComposer prependToFeed />` in `Feed.tsx`) prepends the
  server's response straight into the `['feed']` cache — no forced
  refetch — the same direct-cache-write pattern `TSC-TWEET-002` established
  for profile timelines.

## `Feed` component

[`features/feed/Feed.tsx`](../frontend/src/features/feed/Feed.tsx), mounted
from [`routes/Home.tsx`](../frontend/src/routes/Home.tsx) beneath the
existing signed-in-as/log-out header (`TSC-AUTH-002`).

### States (acceptance criteria)

| State | Rendering |
|---|---|
| Loading (first page) | Three `TweetCardSkeleton`s |
| Error (first page, no cached data) | Full-page `ErrorState` with retry |
| Empty | `EmptyState` ("Your feed is empty…") |
| Populated | `TweetCard` list, deduplicated by id |
| Loading (next page) | A `TweetCardSkeleton` below the sentinel |
| Error (a *later* page) | Inline `ErrorState` below the already-loaded list — loaded tweets are never hidden by a pagination failure |
| End of feed | "You're all caught up." message, sentinel removed |
| Refresh | `Refresh` button in the feed header, `isPending` spinner |
| Newly-created tweet | Composer prepends into the cache directly (see above) |
| Offline | A dismissal-free banner ("You're offline…") from `useOnlineStatus`, independent of query error state |

### De-duplication by id

`items` is built by flattening every fetched page and dropping any tweet id
already seen (`dedupeById` in `Feed.tsx`), keeping the first occurrence. The
backend's keyset pagination never repeats a row within one request, but this
is a defensive guard against a repeat id surfacing from a merged cache (e.g.
paging forward again into a range a previous refresh already covered) —
covered directly by a test that seeds an overlapping second page.

## Pagination: `useInfiniteScrollTrigger`

[`lib/useInfiniteScrollTrigger.ts`](../frontend/src/lib/useInfiniteScrollTrigger.ts)
is a small reusable hook (not feed-specific) wrapping `IntersectionObserver`:
it returns a callback ref for a sentinel element and calls `onLoadMore` when
that sentinel scrolls into view — used here in place of a scroll-event
listener or a "Load more" button (the pattern every other paginated list in
this codebase — `FollowList`, `ReplyList`, `Profile`'s timeline — still
uses; the feed is the first infinite-scroll surface).

Two acceptance criteria hinge on its implementation:

- **"Each next cursor is requested at most once per trigger":** the
  observer callback reads `hasNextPage`/`isFetchingNextPage`/`onLoadMore`
  off a ref (not a closure), so a load only fires when the sentinel's
  intersection *changes* to intersecting **and** no fetch is currently in
  flight — a native `IntersectionObserver` only invokes its callback on
  threshold crossings, not continuously, so a sentinel that stays visible
  after a page loads (e.g. a short page) doesn't refire on its own.
  Verified directly: a test drives a controllable `IntersectionObserver`
  mock, fires three "still intersecting" triggers while a page fetch is
  deliberately kept pending, and asserts exactly one network call.
- **"Observer cleanup prevents requests after unmount":** the callback ref
  disconnects the previous `IntersectionObserver` (if any) before attaching
  a new one, and a `useEffect` cleanup disconnects on unmount — verified by
  asserting `disconnect()` was called after `unmount()`.

## Refresh semantics (human-review focus)

`useRefreshFeed` fetches a single fresh first page directly
(`tweetsApi.getFeed({ limit: 20 })`, no cursor) and **replaces the entire
cached page list** with just that one page — the feed jumps back to the
newest tweets, matching mainstream "pull to refresh" behavior. This is a
deliberate choice over `useInfiniteQuery`'s own `refetch()`, which would
instead re-fetch *every* page currently loaded in memory (most-stale-first)
to keep the whole stack consistent — correct for "resync everything" but a
much heavier and slower action than a user tapping "Refresh" is asking for.

## Scroll-restoration policy (human-review focus)

`App.tsx` uses a plain declarative `<BrowserRouter>` (not a data router), so
React Router's own `<ScrollRestoration>` isn't available.
[`lib/useScrollRestoration.ts`](../frontend/src/lib/useScrollRestoration.ts)
implements the approved policy by hand:

- **Back/forward navigation** (`useNavigationType() === 'POP'` — the
  browser back button, or a tweet detail page's own back action) restores
  the exact `window.scrollY` the feed was at when the user left it, read
  from `sessionStorage` (keyed `scroll-restoration:home-feed`, written
  continuously on scroll and on unmount so a save always lands).
- **Any other arrival** (a fresh page load, or clicking the "Home" nav item
  again) resets to the top (`window.scrollTo(0, 0)`) — explicitly, not just
  "whatever it happened to be" — even if a stale position is still sitting
  in `sessionStorage` from an earlier visit.
- Restoration only runs once the feed actually has content to scroll to
  (`ready: !feed.isLoading`), not against an empty/loading page.

Verified via `tests/routes/Home.test.tsx`: a real `<App />` navigation from
the feed to a tweet's detail page and back (`window.history.back()`)
restores a scrolled position; navigating to Search and then back to Home via
the nav link resets to the top.

## Testing

- **Vitest + RTL + MSW + jest-axe**
  (`frontend/tests/features/feed/Feed.test.tsx`): loading/empty/full-page-
  error-with-retry/pagination-with-dedup/at-most-once-per-trigger/observer-
  cleanup/inline-later-page-error/refresh/newly-created-tweet/offline
  states, plus an accessibility check. Uses a controllable
  `IntersectionObserver` mock (captured instances, manual `trigger(...)`)
  since jsdom has no real implementation; `tests/setup.ts` installs a
  harmless no-op default for every other test file plus `window.scrollTo`/
  `scrollY` stubs (jsdom logs "Not implemented" otherwise and never updates
  `scrollY`), both reset between tests.
- **Vitest + RTL + MSW** (`frontend/tests/routes/Home.test.tsx`): App-level
  integration — the feed renders behind the existing header, and the
  scroll-restoration policy holds across a real browser navigation.
- **Playwright, static build** (`frontend/e2e/feed.spec.ts`): three-
  breakpoint (375/768/1280px) screenshots of a 25-tweet, two-page seeded
  feed — first page, after scrolling to load the second page and reach
  end-of-feed, and the empty state — asserting no horizontal overflow, plus
  a refresh-replaces-first-page check. Screenshots saved to
  `frontend/test-results/screenshots/feed-*.png`.

## Verification commands

```bash
cd frontend
npm run lint            # eslint . — clean (pre-existing warning in App.tsx unrelated)
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean (pre-existing e2e/tweets.spec.ts unrelated)
npm run test:coverage   # vitest run --coverage — 160 tests passed,
                        # 89.85% stmts / 84.75% branch / 86.63% funcs / 91.13% lines
npm run build && npx playwright test   # 35 passed, incl. 7 feed.spec.ts
                        # tests and three-breakpoint feed screenshots
```

## Human review gate

Pending: loading/refresh/empty-feed states and the scroll-restoration
behavior (exact policy documented above).
