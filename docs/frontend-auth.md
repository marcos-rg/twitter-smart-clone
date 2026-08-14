# Frontend authentication (`TSC-AUTH-002`)

Implements register/login/logout, session restoration on reload, and
protected/public route guards for the React SPA, per spec §7.1 (auth &
authorization) and §9.4 (client-side security).

## Token handling

- **Access token:** held only in the in-memory Zustand store
  ([`src/stores/auth-store.ts`](../frontend/src/stores/auth-store.ts)). Never
  written to `localStorage`, `sessionStorage`, IndexedDB, or a JS-readable
  cookie — Zustand's `persist` middleware is deliberately not used here.
- **Refresh token:** never touched by the client. The backend sets it as an
  httpOnly + Secure + SameSite=Strict cookie (`app/routers/auth.py`); the
  client only calls `POST /auth/refresh` with `credentials: 'include'` and
  reads the returned access token from the JSON body.

## HTTP client (`src/api/client.ts`)

A typed `fetch` wrapper (`request<T>(path, options)`) that:

- Attaches `Authorization: Bearer <token>` from the store for `auth: true`
  requests (the default; auth endpoints that must not recurse — register,
  login, refresh — pass `auth: false`).
- Always sends `credentials: 'include'` so the refresh cookie round-trips.
- On a `401` for an authenticated request, calls a **single-flight**
  `refreshAccessToken()` — concurrent 401s share one in-flight
  `POST /auth/refresh` promise — then retries the original request **exactly
  once** (`_isRetry` guard prevents further recursion).
- If refresh fails, calls `useAuthStore.getState().expireSession()`, which
  flips `status` to `unauthenticated` and sets a one-time `sessionExpired`
  flag; it does not redirect itself — that's the route guards' job (see
  below), so there is no redirect loop.
- Throws a typed `ApiError` (status, code, message, details, requestId)
  matching the backend's uniform error envelope (spec §6.2).

## Session store & bootstrap

- `useAuthStore` (Zustand) tracks `status: 'idle' | 'loading' |
'authenticated' | 'unauthenticated'`, the current `user`, and the in-memory
  `accessToken`.
- `useSessionBootstrap()` ([`src/features/auth/hooks.ts`](../frontend/src/features/auth/hooks.ts))
  runs once on `App` mount: calls `POST /auth/refresh` then `GET /auth/me` to
  restore a session across a reload. Any failure (no cookie, expired, network)
  leaves the store `unauthenticated` — no error toast, since this isn't a
  "your session expired" event, just "there's no session."

## Routes & guards (`src/routes/guards/RouteGuards.tsx`)

- `ProtectedRoute` — shows a loading skeleton while `status` is `idle`/`loading`
  (so a valid session never flashes a login screen), redirects to `/login`
  with the attempted location in `router` state once `status` is confirmed
  `unauthenticated`, and renders children once `authenticated`.
- `PublicOnlyRoute` — redirects `/login` and `/register` to `/` once
  `authenticated`, so a signed-in user can't land back on the auth screens.
- `/` is protected (renders `Home`); `/login` and `/register` are
  public-only; `/lab` (the design lab) stays unauthenticated for the human
  review workflow.

## Forms (`src/features/auth/{Login,Register}Form.tsx`)

- Client-side validation mirrors the backend's constraints
  (`app/schemas/auth.py`, `app/models/user.py`: name ≤50 chars, username
  `^[a-zA-Z0-9_]{3,30}$`, password ≥8 chars) for instant feedback; the server
  remains the source of truth.
- Built from the `TSC-UX-001` design-system `Input`/`Button` components, so
  labels, `aria-invalid`/`aria-describedby` wiring, and focus styles come for
  free — forms are keyboard accessible (tab order, Enter submits) and pass
  `jest-axe`.
- Loading state via `Button`'s `loading` prop; failures surface as a toast
  (`useToast`) with the server's user-safe `message`.
- **Registration does not log the user in** — `/auth/register` issues no
  tokens — so success routes to `/login` with the email pre-filled and a
  confirmation toast. This is a deliberate scope decision, not a spec change:
  the backend contract already separates register from login (spec §6.3).

## Expired-session UX

`expireSession()` only sets the one-time `sessionExpired` flag when the
previous status was `authenticated` (a real "your session ran out" event, not
just "you were never logged in"). The `Login` screen reads and immediately
acknowledges that flag on mount, showing "Your session has expired. Please
log in again." exactly once — back/forward navigation won't re-show it.

## Testing

- **Vitest + RTL + MSW** (`frontend/tests/features/auth/`,
  `frontend/tests/routes/auth-flow.test.tsx`): form validation and a11y,
  register → login (with pre-filled email) → reload/restore → logout,
  concurrent-401 single-flight refresh + single retry, failed-refresh
  redirect without a loop, and a direct inspection of
  `localStorage`/`sessionStorage`/`document.cookie` proving the access token
  never lands there. MSW (`tests/mocks/`) intercepts the client's `fetch`
  calls at the network level; `tests/setup.ts` starts/resets/stops the MSW
  server and resets the Zustand store between tests.
- **Playwright** (`frontend/e2e/auth.spec.ts`): renders `/login` and
  `/register` at mobile (390×844) and desktop (1440×900) viewports and saves
  screenshots to `frontend/test-results/screenshots/` as review evidence.
  `e2e/lab.spec.ts` and `e2e/scaffold.spec.ts` were updated for `/` now being
  a protected route (they assert the `/login` redirect instead of the old
  unauthenticated `Home` heading).

## Verification (commands run)

```bash
cd frontend
npm run lint            # eslint . — clean
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean
npm run test:coverage   # vitest run --coverage — 75 tests passed,
                        # 93.88% stmts / 89.31% branch / 93.61% funcs / 95.44% lines
npm run e2e             # playwright test — 8 passed, incl. mobile/desktop
                        # login + register screenshots
```

## Human review gate

Pending: auth copy (form labels, hints, toasts), validation feedback wording,
and the redirect UX (login → intended destination, register → login with
pre-filled email, expired-session messaging) need human sign-off before this
task is marked `Done`.
