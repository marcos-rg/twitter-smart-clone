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

## Full-stack E2E verification (`TSC-AUTH-003`)

- **Playwright, real stack** (`frontend/e2e-auth/auth-flow.spec.ts`,
  `frontend/playwright.auth.config.ts`): runs against the actual
  containerized `frontend` dev server talking to the real `backend`
  container, real PostgreSQL, and real Redis — no mocks. Covers register,
  login, protected navigation (guards redirect correctly both ways), reload/
  session restoration, logout, invalid credentials (wrong password and
  unknown email), duplicate registration, expired-access-token recovery, and
  revoked-refresh-token reuse detection (whole-family revocation). See
  [`docs/auth-threat-checklist.md`](./auth-threat-checklist.md) for how each
  scenario maps to a threat, and `docker-compose.e2e.yml` /
  [`docs/local-dev-stack.md`](./local-dev-stack.md) for how the stack is run.
  `frontend/e2e-auth/fixtures.ts` extends every test with automatic
  assertions: no browser console error, no failed/unhandled request, and no
  access/refresh token leaking into `localStorage`/`sessionStorage`/
  `document.cookie`.
- **Bug found and fixed by this real-browser verification**:
  `useSessionBootstrap` ([`src/features/auth/hooks.ts`](../frontend/src/features/auth/hooks.ts))
  previously gated its terminal `setSession`/`clear` calls on a `cancelled`
  flag set by the effect's cleanup function. Under React 18 `StrictMode`'s
  dev-only double effect invocation, that cleanup ran (marking the in-flight
  bootstrap "cancelled") *before* the `/auth/refresh` + `/auth/me` round trip
  resolved, so the store was left stuck in `loading` forever — every route
  showed the "Restoring your session" skeleton indefinitely in a real
  browser. The Vitest/RTL suite never caught this because it doesn't render
  under `StrictMode`. Fixed by relying solely on the `ranRef` guard (which
  survives the simulated unmount/remount for the same component instance) to
  make bootstrap idempotent, with no cleanup-based cancellation at all.

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
- **Playwright, static build** (`frontend/e2e/auth.spec.ts`): renders `/login`
  and `/register` at mobile (390×844) and desktop (1440×900) viewports and
  saves screenshots to `frontend/test-results/screenshots/` as review
  evidence. No backend runs for this project (see `playwright.config.ts`),
  so it only exercises rendering/layout — functional and full-stack
  end-to-end coverage lives in Vitest/MSW and `frontend/e2e-auth/`
  respectively. `e2e/lab.spec.ts` and `e2e/scaffold.spec.ts` were updated for
  `/` now being a protected route (they assert the `/login` redirect instead
  of the old unauthenticated `Home` heading).
- **Playwright, full stack** (`frontend/e2e-auth/`): see "Full-stack E2E
  verification" above.

## Verification (commands run)

```bash
cd frontend
npm run lint            # eslint . — clean
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean
npm run test:coverage   # vitest run --coverage — 75 tests passed,
                        # 94.11% stmts / 90.08% branch / 93.57% funcs / 95.15% lines
npm run e2e             # playwright test — 8 passed, incl. mobile/desktop
                        # login + register screenshots
```

Full-stack auth verification (`TSC-AUTH-003`, against the real Docker
Compose stack — `docker compose -f docker-compose.yml -f
docker-compose.dev.yml -f docker-compose.e2e.yml up`, then
`npm run e2e:auth`):

```bash
npm run e2e:auth   # playwright test --config=playwright.auth.config.ts
                   # 9/9 passed — run 3 consecutive times, all green
```

Backend suite re-verified in containers alongside this change (`make test`
equivalent): 117 backend tests passed, 98% coverage; `ruff`/`black --check`/
`mypy` all clean.

Also verified inside the actual dev containers (`docker compose -f
docker-compose.yml -f docker-compose.dev.yml run --rm frontend ...`), which
surfaced a pre-existing Docker Compose gotcha fixed alongside this task: the
`frontend_node_modules` named volume ([docker-compose.dev.yml](../docker-compose.dev.yml))
is only populated the first time it's created — rebuilding the image after a
`package.json`/`package-lock.json` change does **not** refresh an
already-populated named volume, so newly added dependencies (like `msw` here)
were missing at runtime even though the image itself was up to date. The
[Makefile](../Makefile)'s `lint`/`test` targets now run `npm ci` inside the
container before each frontend command, self-healing the volume whenever the
lockfile changes.

## Human review gate

Pending: auth copy (form labels, hints, toasts), validation feedback wording,
and the redirect UX (login → intended destination, register → login with
pre-filled email, expired-session messaging) need human sign-off before this
task is marked `Done`.

`TSC-AUTH-003` (full-stack verification) has its own separate human review
gate: a manual auth smoke test against the running stack, before that task
is marked `Done`.
