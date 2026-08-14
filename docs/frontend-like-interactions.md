# Optimistic like/unlike interactions (TSC-LIKE-002)

Frontend slice wiring the tweet-card like button to the like/unlike backend
(`TSC-LIKE-001`, see [`likes-backend.md`](./likes-backend.md)) with an
optimistic update, full rollback, rapid-click protection, and a subtle
reduced-motion-aware animation, replacing the inert `liked_by_viewer`/
`like_count` placeholder shipped by `TSC-TWEET-002`.

## API and types

[`api/likes.ts`](../frontend/src/api/likes.ts) adds `likeTweet`/`unlikeTweet`
(`POST`/`DELETE /tweets/{id}/like`), mirroring `api/follows.ts`'s
`followUser`/`unfollowUser` shape. [`api/types.ts`](../frontend/src/api/types.ts)
gained `LikeRelationship` (`{ liked, like_count }`), the like-endpoint
equivalent of `FollowRelationship`.

## Cache fan-out: `patchTweetEverywhere`

A single tweet can be cached in an unbounded number of places at once — its
own `tweetQueryKey`, the home feed, any number of per-user timelines, and any
number of per-parent replies lists — and the set of usernames/parent ids
currently cached isn't known up front. So instead of an enumerated list of
query keys (which is how `useFollowMutation` gets away with updating a single
profile cache entry), the new cache helpers in
[`features/tweets/hooks.ts`](../frontend/src/features/tweets/hooks.ts) match
every cached query **by key shape** — `'feed'` / `'user-tweets'` /
`'tweet-replies'` as the first key segment, matching
`feedQueryKey`/`userTweetsQueryKey`/`repliesQueryKey` — and patch the
matching `TweetView` wherever it appears:

- `patchTweetEverywhere(queryClient, id, patch)` applies `patch` to tweet
  `id` in its own `tweetQueryKey` cache and every currently-cached
  feed/timeline/replies list that contains it. A no-op wherever the tweet
  isn't present (in particular, it never *creates* a cache entry for a page
  that was never visited).
- `snapshotTweetCaches`/`restoreTweetCaches` capture and restore the exact
  `{queryKey, data}` pairs for every cache location holding the tweet, so a
  failed mutation can roll back precisely — not just flip a flag back, which
  would leave a `like_count` off by one if two different cached copies had
  drifted before the click.

## `useLikeMutation`

`useLikeMutation(tweetId)` mirrors `useFollowMutation`'s optimistic-update
shape:

- **`onMutate`**: cancels in-flight queries for the tweet and every
  list-shaped cache (so a background refetch can't clobber the optimistic
  write), snapshots every cache location currently holding the tweet, then
  flips `liked_by_viewer` and adjusts `like_count` by exactly one everywhere
  the tweet is cached — `Math.max(0, …)` clamps the count so a decrement can
  never go negative.
- **`onError`**: restores every touched cache entry to its exact
  pre-mutation snapshot.
- **`onSuccess`**: replaces the optimistic guess with the server's
  authoritative `liked`/`like_count` everywhere the tweet is cached — this is
  what reconciles a stale cache (e.g. the feed's copy already showed liked
  from an earlier action, but the tweet-detail cache didn't) to one
  consistent truth, and is also what makes a same-state idempotent repeat
  call a no-op rather than double-incrementing.

## `LikeButton`

[`LikeButton`](../frontend/src/features/tweets/LikeButton.tsx), rendered by
`TweetCard` in place of the old inert placeholder:

- **Not liked:** outline heart (♡), `aria-pressed="false"`.
- **Liked:** filled heart (❤) in the danger color, `aria-pressed="true"`.
- **Pending:** the button is `disabled` while its mutation is in flight.
- **Failed:** the click rolls all the way back (via `useLikeMutation`'s
  `onError`) and an accessible (`role="alert"`) toast reports it, e.g.
  "Couldn't like this tweet. Too many requests."

**Rapid-click protection**, identical to `FollowButton`: a synchronous
`useRef` guard blocks a second submit fired before React commits the state
update backing `isPending`, so two clicks dispatched in the same tick can't
both fire a request (covered by a test asserting exactly one network call
after two rapid clicks) — combined with the `Math.max(0, …)` clamp in
`useLikeMutation`, a burst of clicks can neither race a duplicate request
past this guard nor drive the cached count below zero if it somehow did.

**Animation**: a brief "pop" (`animate-like-pop`, defined in
[`index.css`](../frontend/src/index.css)) plays on the heart glyph only when
a like newly lands (not on mount of an already-liked tweet, and not on
unlike). It's purely decorative (`aria-hidden`) and disabled twice over for
`prefers-reduced-motion`: the app-wide reduced-motion rule clamps every
animation to 0.01ms, and the glyph's own `motion-reduce:animate-none`
utility drops the animation outright as a second, explicit layer (the same
belt-and-suspenders pattern `Button`'s loading spinner already uses).

## Testing

- **Vitest + RTL + MSW** (`tests/features/tweets/useLikeMutation.test.tsx`):
  unit tests against a bare `QueryClient` (no rendered UI) that seed every
  cache shape (`tweetQueryKey`, feed, user timeline, replies list) with the
  same tweet and assert the mutation's fan-out precisely — success updates
  every cache, a stale cache reconciles to the server-authoritative count on
  an idempotent repeat, a forced failure restores every cache to its exact
  snapshot, and an already-zero count never goes negative on unlike.
- **Vitest + RTL + MSW + jest-axe** (`tests/routes/LikeInteractions.test.tsx`):
  `<App/>`-level integration tests — button states (outline/filled,
  `aria-pressed`), optimistic like/unlike, full rollback with an accessible
  error toast on a forced `429`, the rapid-double-click-fires-once case, the
  "pop" animation (and its `motion-reduce` override) firing only on a
  newly-landed like, cross-cache consistency between the feed and an
  already-visited tweet-detail cache, and a `jest-axe` accessibility check.
  `tests/mocks/handlers.ts` gained default `POST`/`DELETE
  /tweets/:tweetId/like` handlers (idempotent success).
- **Vitest + RTL** (`tests/components/tweet/TweetCard.test.tsx`): updated to
  wrap `TweetCard` in a `QueryClientProvider`/`ToastProvider` (it now always
  renders a live `LikeButton`) and to assert the liked state via
  `aria-pressed` instead of the old "inert placeholder" framing.
- **Playwright, static build** (`frontend/e2e/likes.spec.ts`): screenshots
  and assertions for the liked, unliked, pending (disabled button, mocked
  slow response), failed (rollback + `role="alert"` toast, mocked `429`),
  and reduced-motion (`emulateMedia({ reducedMotion: 'reduce' })`, asserting
  the heart glyph's computed `animationDuration` is clamped to <0.001s)
  states, saved to `frontend/test-results/screenshots/like-*.png`.

## Verification commands

```bash
cd frontend
npm run lint            # eslint . — clean (pre-existing App.tsx fast-refresh warning only)
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean (pre-existing e2e/feed.spec.ts,
                        # e2e/tweets.spec.ts warnings predate this task)
npm run test:coverage   # vitest run --coverage — 173 tests passed,
                        # 90.12% stmts / 84.77% branch / 87.12% funcs / 91.37% lines
npm run e2e             # npm run build && playwright test — 40 passed, incl.
                        # 5 new like-state screenshots
```

## Human review gate

Pending: the optimistic like/unlike interaction (button states, rollback
behavior and toast copy, rapid-click handling) and the "pop" animation
(amplitude, duration, and reduced-motion behavior).
