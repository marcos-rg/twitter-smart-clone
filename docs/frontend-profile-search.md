# Profile, profile-edit, and search interfaces (TSC-USER-002)

Frontend slice for viewing/editing profiles and searching for users, built on
top of the `/api/v1/users/*` backend (`TSC-USER-001`) and the auth/design
system foundations (`TSC-AUTH-002`, `TSC-UX-001`).

## Routes

- `/profile/:username` ([`src/routes/Profile.tsx`](../frontend/src/routes/Profile.tsx)) —
  own or another user's profile: header (avatar, name, `@handle`, bio, join
  date) plus their tweet timeline, cursor-paginated. "Edit profile" only
  renders when `:username` matches the signed-in user (case-insensitively,
  matching backend username uniqueness).
- `/profile/:username/edit` ([`src/routes/ProfileEdit.tsx`](../frontend/src/routes/ProfileEdit.tsx)) —
  edit form for the signed-in user's own profile. Visiting this for anyone
  else redirects to the read-only profile instead of rendering a form that
  could edit the wrong account.
- `/search` ([`src/routes/Search.tsx`](../frontend/src/routes/Search.tsx)) —
  exact/prefix/fuzzy user search with a debounced query and cursor
  pagination.

All three require an authenticated session (`ProtectedRoute`, matching
`/api/v1/users/*`'s `get_current_user` dependency). `AppShell`'s nav gained
**Search** (always, once signed in) and **Profile** (linking to the
signed-in user's own profile) entries.

## Never expose email on a public profile

`GET /users/{username}` never returns an `email` field, for the owner or
anyone else (verified by `TSC-USER-001`'s backend tests). The frontend
enforces this at the type level, not just by convention:
[`UserPublicProfile`](../frontend/src/api/types.ts) has no `email` field at
all, so `ProfileHeader` (used for both own and other profiles) cannot
reference one — a compile error, not a runtime check. The edit screen instead
seeds its form directly from the in-memory auth store's `user` (already the
full private shape from login/session restore), avoiding a second round trip
that still wouldn't carry an email anyway.

## Editing

[`ProfileEditForm`](../frontend/src/features/users/ProfileEditForm.tsx)
mirrors the backend's validation
([`app/models/user.py`](../backend/app/models/user.py),
[`app/schemas/users.py`](../backend/app/schemas/users.py)) client-side: name
1–50 chars, username `^[a-zA-Z0-9_]{3,30}$`, email format, bio ≤ 160 chars
(name/username/email rules are imported from `features/auth/validation`
rather than duplicated). Field state is seeded once via a lazy `useState`
initializer and never re-derived from a background refetch, so a failed save
(e.g. a `409` username/email conflict) leaves the user's in-progress edits
exactly as typed instead of resetting them to the stale server values.

On success, [`useUpdateProfile`](../frontend/src/features/users/hooks.ts)
refreshes the in-memory auth store (so the header/nav reflect a rename
immediately) and the profile query cache, then the screen navigates to
`/profile/<possibly-new-username>`.

`ProfileEdit`'s "only the owner may edit" guard is evaluated once at mount
(not reactively on every render): a successful save changes the auth store's
`user.username` via this same screen's mutation, and re-deriving the guard
from the *live* store value on the resulting re-render would see the
still-old `:username` route param next to the already-new store username,
look like "editing someone else's profile," and redirect to the stale
old-username profile before the real post-save navigation lands.

## Search

[`Search`](../frontend/src/routes/Search.tsx) debounces the typed query
(300ms, [`useDebouncedValue`](../frontend/src/lib/useDebouncedValue.ts))
before it drives [`useUserSearch`](../frontend/src/features/users/hooks.ts),
a TanStack Query `useInfiniteQuery` keyed on `[mode, debouncedQuery]`. Mode
selection ([`SearchModeSelector`](../frontend/src/features/users/SearchModeSelector.tsx))
applies immediately, no debounce.

**No stale results from an older request:** the hook deliberately does not
set `placeholderData`/`keepPreviousData`. Each distinct `(mode, query)` pair
is its own query-cache entry with its own loading state — when the debounced
query changes, the UI shows a loading state for the *new* key rather than the
previous key's (possibly now-outdated) results, and an in-flight response for
an abandoned key updates a cache entry nothing is subscribed to anymore. This
is covered directly by a test that types a query, lets a deliberately slow
mocked response start, types further before it resolves, and asserts the
slow response's data never appears once it eventually lands.

Loading, no-results, error (with retry), and "Load more" pagination states
are each rendered from the query's own status flags
(`isLoading` / `isError` / empty `data` / `hasNextPage`).

## Testing

- **Vitest + RTL + MSW + jest-axe**
  (`frontend/tests/routes/Profile.test.tsx`,
  `frontend/tests/routes/ProfileEdit.test.tsx`,
  `frontend/tests/routes/Search.test.tsx`,
  `frontend/tests/features/users/SearchModeSelector.test.tsx`): own/other
  profile rendering and the no-email guarantee, edit validation/success/
  conflict-preserves-input/unauthorized-edit-redirect, and search mode/query/
  loading/no-results/error/pagination/stale-request behavior, all with
  `jest-axe` accessibility checks. `tests/setup.ts` now also resets
  `window.history` to `/` between tests, since `App` mounts a real
  `BrowserRouter` that reads `window.location` at mount and jsdom's `window`
  (and its history) is shared across every test in a file.
- **Playwright, static build** (`frontend/e2e/profile-search.spec.ts`):
  mocks the auth bootstrap and `/users/*` calls via `page.route` (no backend
  runs for this project — see `playwright.config.ts`) and renders the
  profile, profile-edit, and search screens at the three product breakpoints
  (375/768/1280px), asserting no horizontal overflow (before and after
  scrolling) and saving full-page screenshots to
  `frontend/test-results/screenshots/`. Full-stack behavior against the real
  API and database is `TSC-USER-003`.

## Verification commands

```bash
cd frontend
npm run lint            # eslint . — clean
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean
npm run test:coverage   # vitest run --coverage — 97 tests passed,
                        # 92.71% stmts / 87.97% branch / 92.75% funcs / 93.81% lines
npm run e2e             # npm run build && playwright test — 17 passed, incl.
                        # profile/profile-edit/search screenshots at 3 breakpoints
```

## Human review gate

Pending: profile information hierarchy (what's shown, in what order, on own
vs. other profiles) and search behavior (mode selection UX, debounce
timing, result presentation).
