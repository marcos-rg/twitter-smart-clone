# Tweet composer, cards, detail, replies, and timelines (TSC-TWEET-002)

Frontend slice on top of the tweet/reply/timeline backend (`TSC-TWEET-001`,
see [`tweet-backend.md`](./tweet-backend.md)): the tweet composer, the
`TweetCard` presentational component, the tweet-detail/reply screen, and the
profile timeline updated to render the real `TweetView` contract instead of
the placeholder shape it shipped with.

Retweets/quote-tweets/reposts are out of scope (spec: excluded from this
project). Liking is now wired to `POST`/`DELETE /tweets/{id}/like` with an
optimistic update and rollback — see
[`frontend-like-interactions.md`](./frontend-like-interactions.md)
(`TSC-LIKE-002`). The main chronological feed is a later slice — see
[`frontend-feed.md`](./frontend-feed.md) (`TSC-FEED-002`), which reuses
`TweetCard`/`TweetComposer` from this task unchanged.

## Corrected API types

[`api/types.ts`](../frontend/src/api/types.ts) replaced the stale
`UserTimelineItem`/`UserTimelineResponse` pair (which predated
`TSC-TWEET-001` and only had `author_id`, no `author`/`media`/`links`/
`liked_by_viewer`) with `TweetAuthor`, `TweetMediaOut`, `LinkEntity`,
`TweetView`, `TweetCreateRequest`, and `TweetListResponse`, matching
`backend/app/schemas/tweets.py` field-for-field. [`api/users.ts`](../frontend/src/api/users.ts)'s
`getUserTweets` now returns `TweetListResponse`, and a new
[`api/tweets.ts`](../frontend/src/api/tweets.ts) adds `createTweet`,
`getTweet`, and `listReplies`, all rendering/consuming the same `TweetView`
shape as the profile-timeline endpoint (the backend guarantees this — all
four tweet-reading endpoints share one `TweetsService`).

## Composer whitespace/counter contract

[`TweetComposer`](../frontend/src/features/tweets/TweetComposer.tsx)'s
character counter (`N / 280`) mirrors the backend's exact validation rule
(`TweetCreateRequest._validate_content`, `docs/tweet-backend.md`): leading/
trailing whitespace is stripped before counting, and the 280-character limit
applies to that stripped length — not the raw textarea value. Internal
whitespace and newlines are left untouched in what's submitted; only the
*count* strips. The counter turns bold/foreground near the limit and
danger-colored once over it, and the submit button is disabled whenever the
stripped content is empty, over 280, an image upload is still
`uploading`/`confirming` (tracked via a new `onItemsChange` callback added to
`useImageUploader`/`ImageUploader` for exactly this purpose), or a submit is
already in flight.

**Recoverable-failure contract:** only a successful `POST /tweets` clears
the composer. A thrown `ApiError` (or network error) from `useCreateTweet`
is caught in the composer's submit handler, surfaced via `useToast`
(`describeTweetsError`, mirroring `describeUsersError`/
`describeFollowsError`), and the typed content plus any uploaded/in-progress
images are left exactly as they were — verified by
`tests/features/tweets/TweetComposer.test.tsx`'s forced-500 test asserting
the textarea still has the typed value afterward.

The composer is reused for both a new root tweet (`Profile.tsx`, no
`parentTweetId`, `profileUsername` set so the post lands in that profile's
timeline cache) and a reply (`TweetDetail.tsx`, `parentTweetId` set, no
`profileUsername`).

## Safe-link rendering — no `dangerouslySetInnerHTML`, ever

[`components/tweet/linkify.ts`](../frontend/src/components/tweet/linkify.ts)
splits a tweet's `content` into text/link segments using only the server's
`links: {url, start, end}[]` spans — the same safe-link contract documented
in `tweet-backend.md` (only `http`/`https` spans the backend's own regex
extracted, trailing punctuation trimmed, `javascript:`/`data:`/bare
scheme-relative URLs never present). The helper only ever **slices**
`content`; it never interprets any substring as markup, so it can't be
tricked into producing a link from raw text a malicious author typed (e.g.
`<script>...</script>` or `javascript:alert(1)` typed as plain text stays
plain text — the backend never emitted a span for it). `TweetCard` renders
each segment as a React text node (`<span>`) or a real
`<a href target="_blank" rel="noopener noreferrer">` for link segments —
`dangerouslySetInnerHTML` is not used anywhere in this task's code.
`tests/components/tweet/TweetCard.test.tsx`'s "never turns malicious content
into executable markup" test asserts directly against `container.innerHTML`
that no `<script>`, `[onerror]`, or `javascript:`-href element is ever
produced from tweet content, whether or not the backend supplied link spans
for it.

## Flat-reply / no-nested-reply UI rule

The backend rejects replying to a reply with `422` (`CannotReplyToReplyError`
— a reply can never itself be replied to). `TweetDetail.tsx` enforces the UI
side of this: it only renders a `TweetComposer` (with `parentTweetId`) when
the fetched tweet's own `parent_tweet_id === null`. When the tweet being
viewed is itself a reply, no reply composer or "reply to this" control is
shown at all — there's simply a flat (always-empty) replies list below it,
consistent with `GET /tweets/{id}/replies` on a reply always returning an
empty page rather than an error. Covered by
`tests/routes/TweetDetail.test.tsx`'s "does not render a reply composer when
the tweet is itself a reply" test.

## Cache-update strategy on tweet/reply creation

[`features/tweets/hooks.ts`](../frontend/src/features/tweets/hooks.ts)'s
`useCreateTweet` updates React Query caches directly from the `POST /tweets`
response — no forced refetch:

- The new tweet is cached at its own `tweetQueryKey(id)` (a follow-up
  `useTweet(id)` navigation doesn't refetch).
- A reply (`parent_tweet_id` set) is prepended to the parent's cached
  `repliesQueryKey(parentId)` `useInfiniteQuery` cache, and the parent's own
  cached `TweetView` at `tweetQueryKey(parentId)` (if present) gets
  `reply_count` bumped by 1 — both via `queryClient.setQueryData`, matching
  the optimistic-cache-write pattern already used by
  `features/follows/hooks.ts`'s `useFollowMutation`.
- A root tweet posted with a `profileUsername` (the profile-page composer)
  is prepended to that profile's `userTweetsQueryKey` timeline cache —
  the same key shape `features/users/hooks.ts`'s `useUserTweets` uses, so
  the write lands in the exact cache entry the profile screen reads.

`Profile.tsx`'s composer test asserts a posted tweet appears in the timeline
and the "No tweets yet" empty state disappears **without an additional
`GET /users/:username/tweets` request** — confirming the cache write, not a
refetch, is what updates the UI.

## `TweetCard` and the image gallery

[`TweetCard`](../frontend/src/components/tweet/TweetCard.tsx) now takes a
full `TweetView` (author already embedded — no separate author fetch) and
removed the leftover repost action from the earlier scaffold (out of
scope). The whole card navigates to `/tweet/{id}` on click; the author name
links to their profile and the timestamp links to the tweet — both real
`<Link>`s so keyboard/screen-reader users have an actual accessible
navigation target, not just a mouse-only card-level handler — and every
other interactive descendant (content links, the reply button, `LikeButton`)
calls `stopPropagation` so it doesn't also trigger the card navigation. See
[`frontend-like-interactions.md`](./frontend-like-interactions.md) for
`LikeButton` itself (`TSC-LIKE-002`).

[`TweetImageGallery`](../frontend/src/components/tweet/TweetImageGallery.tsx)
renders a tweet's 0-4 images (ordered by `position`) in a responsive grid: 1
image full-width, 2 side-by-side, 3 as a large left image with two stacked
on the right (`grid-cols-2` + `row-span-2` on the first tile), 4 as a 2x2
grid. There's no alt-text field on `TweetMediaOut` (only
`key`/`content_type`/`position`), so each image gets a positional fallback
alt (`"Tweet image N"`) rather than inventing a field the API doesn't
return.

## Testing

- **Vitest + RTL** (`tests/features/tweets/linkify.test.ts`): offset
  splitting, adjacent/boundary spans, malformed/overlapping/out-of-range
  span defensiveness, and the "no span ⇒ no link, ever" guarantee.
- **Vitest + RTL + MSW** (`tests/features/tweets/TweetComposer.test.tsx`):
  live counter against the stripped-whitespace rule, blank/over-limit submit
  disabling, content preserved + toast shown on a forced `500`, and a
  full presign→upload→confirm→submit flow (via an injectable
  `imageUploadAdapter`, the same seam `AvatarUploader` already uses) that
  asserts the posted `media_keys` match upload order and the composer
  clears only on success.
- **Vitest + RTL + jest-axe**
  (`tests/components/tweet/TweetCard.test.tsx`): author/content/action
  rendering, long-content wrapping, avatar-initials fallback, 4-image
  gallery ordering, real link rendering from server-supplied spans, the
  malicious-content-stays-inert assertion, click-to-navigate, and
  accessibility.
- **Vitest + RTL + MSW**
  (`tests/routes/TweetDetail.test.tsx`): root tweet with reply composer and
  replies rendered, no reply composer on a reply's own detail page, and a
  404 rendering a real `ErrorState` rather than crashing.
- **Vitest + RTL + MSW** (`tests/routes/Profile.test.tsx`, extended): the
  composer's presence/absence and the no-refetch cache-write assertion
  described above, plus the pre-existing own/other-profile and pagination
  coverage updated to the real `TweetView` fixture shape.
- **Playwright** (`e2e/tweets.spec.ts`, new; `e2e/profile-search.spec.ts`,
  fixtures updated to the real `TweetView` shape): composer + image-bearing
  card on the own profile, and the tweet-detail page with its reply composer
  and two flat replies (one with a rendered link), at the three standard
  breakpoints (375/768/1280px), each asserting no horizontal overflow and
  saving a screenshot to `test-results/screenshots/tweet-*-<breakpoint>.png`.

## Verification commands run

- `npm run typecheck` (`tsc -b --noEmit`) — clean.
- `npm run lint` (`eslint .`) — clean (one pre-existing, unrelated
  `react-refresh/only-export-components` warning on `App.tsx`).
- `npx vitest run` — 24 test files, 148 tests passed.
- `npm run build` (`tsc -b && vite build`) — clean; required before running
  Playwright locally, since `playwright.config.ts`'s `webServer` serves the
  built `dist/` via `vite preview`, not source.
- `npx playwright test --project=chromium` — 28 tests passed, including the
  6 new `e2e/tweets.spec.ts` tests and the updated `e2e/profile-search.spec.ts`
  fixtures.
- `npm run format` — applied Prettier formatting to the new/changed files.
