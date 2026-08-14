# Follow and social-list interfaces (TSC-SOC-002)

Frontend slice for following/unfollowing a profile and browsing follower/
following lists, built on top of the `/users/{username}/follow`,
`/followers`, and `/following` backend (`TSC-SOC-001`) and the profile
screens (`TSC-USER-002`).

## Follow-state fields on `UserPublicProfile`

[`UserPublicProfile`](../frontend/src/api/types.ts) gained
`followers_count`, `following_count`, and `is_following` — the same fields
`GET /users/{username}` now returns (`TSC-SOC-001`). They're plain
`number`/`boolean` fields (not optional) so every profile-rendering call
site gets a real value rather than having to guard against `undefined`.

## `FollowButton`

[`FollowButton`](../frontend/src/features/follows/FollowButton.tsx),
rendered by [`ProfileHeader`](../frontend/src/features/users/ProfileHeader.tsx)
in place of "Edit profile" for any profile that isn't the signed-in user's
own:

- **Own profile:** renders nothing — self-follow is impossible on the
  backend, so there's no control to show.
- **Not following:** solid "Follow" button.
- **Following:** outline "Following" button (`aria-pressed="true"`);
  clicking it unfollows.

**Optimistic update + full rollback:**
[`useFollowMutation`](../frontend/src/features/follows/hooks.ts) flips the
cached profile's `is_following` and `followers_count` in `onMutate`, before
the network call resolves, so the button and the header's follower count
update immediately. On failure, `onError` restores the *exact*
pre-mutation snapshot (not just `is_following`) — a failed follow/unfollow
never leaves the count off by one — and `FollowButton` shows an error toast
via the shared `useToast` (e.g. "Couldn't follow @bob. Too many requests.").
On success, the server's authoritative `following`/`followers_count`
replace the optimistic guess, which matters for idempotent repeat calls
where the count doesn't move.

**Rapid-click protection:** a synchronous `useRef` guard in `FollowButton`,
not just the mutation's `isPending` flag, blocks a second submit from a
fast double click. `isPending` only becomes `true` after React commits the
state update `mutate()` schedules, so two clicks dispatched in the same
tick would both read `isPending: false` and both fire a request without
this guard — covered directly by a test asserting exactly one network call
after two rapid clicks.

## Follower/following lists

[`FollowList`](../frontend/src/features/follows/FollowList.tsx), routed at
`/profile/:username/followers` and `/profile/:username/following`
([`routes/Followers.tsx`](../frontend/src/routes/Followers.tsx),
[`routes/Following.tsx`](../frontend/src/routes/Following.tsx)): a
cursor-paginated user list (`useFollowers`/`useFollowing`,
`useInfiniteQuery`), with a two-tab `NavLink` switcher at the top that
doubles as the route's own navigation.

- Each route keeps its own TanStack Query cache
  (`['followers', username]` / `['following', username]`), so switching
  from "Followers" to "Following" and back preserves whatever pages of
  "Followers" were already fetched instead of resetting to page one.
- List rows reuse [`UserCard`](../frontend/src/features/users/UserCard.tsx)
  (link-to-profile only) rather than rendering their own follow/unfollow
  control: `FollowUserItem` (the backend's `/followers`/`/following` row
  shape) has no `is_following` field — the backend doesn't compute the
  signed-in caller's relationship to every row of someone else's follower
  list — so a per-row button here would have to guess.
- The profile header's "N Following" / "N Followers" counts link directly
  to these routes.

## Testing

- **Vitest + RTL + MSW + jest-axe**
  (`frontend/tests/routes/FollowInteractions.test.tsx`): no-control-on-own-
  profile, Follow/Following control states, optimistic follow + full
  rollback on a forced `429`, the rapid-double-click-fires-once case,
  followers-list navigation from the profile header, cursor pagination
  without duplicate rows, tab-switch cache preservation, empty/error list
  states, and `jest-axe` accessibility checks on both the button and the
  list. `frontend/tests/mocks/handlers.ts` gained default `/follow`,
  `/followers`, and `/following` handlers plus `followers_count`/
  `following_count`/`is_following` on the default profile mock; existing
  `Profile.test.tsx`/`ProfileEdit.test.tsx` fixtures for other-user
  profiles were updated to include the same three fields so they stay
  representative of the real response shape.
- **Playwright, static build** (`frontend/e2e/profile-search.spec.ts`):
  extends the existing profile/search spec with mocked `/followers` and
  `/following` routes and a three-breakpoint (375/768/1280px) screenshot
  test for the followers screen, asserting no horizontal overflow before
  and after scrolling, saved to `frontend/test-results/screenshots/`.

## Verification commands

```bash
cd frontend
npm run lint            # eslint . — clean
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean
npm run test:coverage   # vitest run --coverage — 108 tests passed,
                        # 92.25% stmts / 86.46% branch / 91.83% funcs / 93.63% lines
npm run e2e             # npm run build && playwright test — 20 passed, incl.
                        # followers screenshots at 3 breakpoints
```

## Human review gate

Pending: the optimistic follow/unfollow interaction (button states, rollback
behavior, toast copy) and follower/following list navigation (tab switching,
pagination, and count-link entry points from the profile header).
