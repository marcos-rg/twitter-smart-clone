# Realtime notifications interface (TSC-NOTIF-002)

Frontend slice wiring the persisted notifications API (`TSC-NOTIF-001`, see
[`notifications-backend.md`](./notifications-backend.md)) and the
authenticated WebSocket transport (`TSC-NOTIF-004`, see
[`websocket-realtime.md`](./websocket-realtime.md)) into a notifications
panel, an unread nav badge, and a client-side WebSocket client with
reconnect/backoff/heartbeat and de-duplication against REST.

## Layout

```
frontend/src/
├── api/
│   ├── types.ts                          # NotificationItem/Event/... types
│   └── notifications.ts                  # listNotifications, markNotificationsRead, websocketUrl
├── stores/
│   └── notifications-store.ts            # zustand: unreadCount + connectionStatus
├── features/notifications/
│   ├── ws-client.ts                      # NotificationsSocket: reconnect/backoff/heartbeat
│   ├── hooks.ts                          # query/mutation hooks, cache patching, socket bridge hook
│   ├── NotificationRow.tsx               # one row: actor, verb, unread dot, mark-read-on-open
│   └── NotificationsPanel.tsx            # list/panel: states, pagination, mark-selected/all
├── routes/Notifications.tsx              # thin route wrapper, `/notifications`
├── components/layout/AppShell.tsx        # nav item + unread badge (updated)
└── App.tsx                               # NotificationsSocketBridge (updated)
```

## `NotificationsSocket` (`features/notifications/ws-client.ts`)

A small, dependency-injectable client for `GET /api/v1/ws` — no framework
dependency (no React, no TanStack Query), so it's unit-testable against a
fake `WebSocket` with fake timers (`tests/features/notifications/ws-client.test.ts`).

- **Auth:** `getToken()` is called fresh on every (re)connect attempt rather
  than captured once — access tokens are short-lived and rotate via
  `POST /auth/refresh`, so a token captured at construction time could go
  stale across a reconnect.
- **Reconnect/backoff:** any non-explicit close schedules a reconnect after
  `minBackoffMs * 2^attempt`, capped at `maxBackoffMs` (production defaults:
  1s → 2s → 4s → … → capped at 30s). The attempt counter resets to 0 as soon
  as a connection opens successfully, so a connection that's stable for a
  while doesn't carry forward a long backoff from an earlier blip.
- **Heartbeat:** replies `{"type":"pong"}` to the server's `{"type":"ping"}`
  (`docs/websocket-realtime.md`'s documented contract) — any other frame with
  `type: "notification"` is forwarded to `onEvent`; anything else (malformed
  JSON, unknown `type`) is silently ignored.
- **Reconnect-restores-state contract:** the server holds no per-connection
  session to resume (missed events are never replayed over the socket) —
  `onReconnected` fires only on a *second* open (not the first) so the
  caller can reconcile via `GET /notifications`.
- **No leaked sockets/timers:** `disconnect()` clears any pending reconnect
  timer, detaches every handler on a live socket before closing it, and
  never reconnects again until `connect()` is called anew. Idempotent —
  safe to call before any `connect()`, or twice in a row.

## Cache/store design (`features/notifications/hooks.ts`)

The paginated list lives in TanStack Query (`notificationsQueryKey() ===
['notifications']`, an `useInfiniteQuery` mirroring `useReplies`/`useFeed`'s
shape). The unread badge lives in its own tiny zustand store
(`stores/notifications-store.ts`) rather than being derived from the list
query, for two reasons: it needs to be correct *before* the panel has ever
been opened (see "badge priming" below), and it's simpler to reset
atomically on logout than to reach into an arbitrary query cache shape.

- **`useNotifications()`**: the paginated list. Syncs the store's
  `unreadCount` from the server-authoritative `unread_count` every time a
  fresh first page lands (initial load, manual refetch, or the
  reconcile-after-reconnect refetch below).
- **`applyNotificationEvent(queryClient, event)`**: applies a live WebSocket
  event — bumps the unread count, and, if the list has already been fetched
  at least once, prepends it to the first cached page too. De-duplicated
  against both the cached list (an item also returned by REST) and a
  session-scoped `seenLiveNotificationIds` set (a duplicate live
  redelivery, e.g. after a reconnect, with no cache to check against), so a
  follow/like/reply event renders/counts exactly once (acceptance
  criterion). `resetLiveNotificationDedupe()` clears that set on logout.

  **Bug fixed during this task's review**: the badge bump originally rode
  on `queryClient.setQueryData`'s return value, which is only truthy when
  there was an existing `['notifications']` cache entry to patch — but that
  cache doesn't exist until `useNotifications` (i.e. the panel) has been
  mounted at least once. The practical effect: a signed-in user who never
  opened the notifications panel never saw the unread badge move at all,
  no matter how many live events arrived — reported directly after the
  first pass shipped ("I only start getting notifications if I click the
  notification page"). Fixed by decoupling the badge bump from whether a
  list cache exists to prepend into; a live push is new information the
  moment it arrives regardless, and the list's own next fetch reconciles
  the badge to the server-authoritative `unread_count` either way.
- **`useMarkAllNotificationsRead()` / `useMarkSelectedNotificationsRead()`**:
  mutations wrapping `POST /notifications/read`, patching every matching
  cached row's `is_read` and syncing the store's `unreadCount` from the
  response on success.
- **`useNotificationsSocket()`** (mounted once via `NotificationsSocketBridge`
  in `App.tsx`): owns the socket's lifecycle.
  - Connects only while the auth store's `status === 'authenticated'`.
  - On reconnect, invalidates the `['notifications']` query so it refetches
    and reconciles against the DB.
  - **Logout** (status leaves `'authenticated'`): disconnects the socket,
    resets the unread store, and removes the `['notifications']` query —
    the acceptance criterion "logout closes the socket and clears
    user-specific notification state," so the next signed-in user on the
    same tab never sees a flash of the previous user's notifications.
  - The effect's cleanup always disconnects the socket it created, so
    unmounting (or `status` changing) never leaks a connection or its
    reconnect timer.
  - **Badge priming**: fires one cheap `GET /notifications?limit=1` as soon
    as a session is authenticated, purely to read `unread_count` into the
    store — independent of the `['notifications']` list cache (so it can't
    conflict with `useNotifications`' own pagination of that same key) and
    independent of the socket (only *future* events arrive there). Without
    this, the nav badge would stay at 0 until the panel was opened at least
    once, even though a real unread count existed server-side.

## `NotificationsPanel` / `NotificationRow`

- **States:** loading skeletons, a full-page retryable error (first page
  only — a later page failure isn't currently distinguished, matching the
  task's scope), an empty state, and cursor-paginated "Load more" /
  "You're all caught up." (same pattern as `FollowList`/`Feed`).
  A `role="status"` "Reconnecting…" banner surfaces
  `useNotificationsStore`'s `connectionStatus` without blocking the
  already-loaded list.
- **Read actions:** a checkbox per row plus "Mark selected read"/"Mark all
  read" buttons (disabled when nothing is selected / nothing is unread).
  Opening an unread row (a real `<button>` covering the row) marks it read
  and navigates to the relevant destination — a follow goes to the actor's
  profile; a like/reply goes to the tweet (`/tweet/{tweet_id}`), falling
  back to the actor's profile if `tweet_id` is somehow absent.
- **Keyboard behavior:** every interactive element (checkbox, row button,
  mark-read buttons, "Load more") is a native `<input>`/`<button>` — no
  custom roving-tabindex or keydown handling, so standard Tab/Space/Enter
  operability comes for free (asserted directly in
  `NotificationsPanel.test.tsx`).

## Nav badge (`components/layout/AppShell.tsx`)

A "Notifications" nav item (only shown once a session is authenticated,
alongside "Profile") with an unread-count pill, in both the desktop sidebar
and the mobile bottom bar.

**Accessibility fix found during this task**: the desktop sidebar's visible
label ("Notifications") is `hidden` below the `lg` breakpoint, and the
icon-only breakpoint has an `sr-only` fallback label — but that fallback was
originally *also* `lg:hidden`, so at desktop width the accessible name
reduced to just "Notifications" with no unread count at all, even though
the badge was visible on screen. Fixed by setting `aria-label` directly
(`"Notifications, 3 unread"`) whenever there's a badge, on both the desktop
and mobile links, and marking the now-redundant content spans `aria-hidden`
in that case — caught by an `e2e/notifications.spec.ts` run at desktop width
(`getByRole('link', { name: /notifications, 2 unread/i })` found nothing
until this fix), not by the Vitest/jsdom suite, since jsdom doesn't apply
the compiled Tailwind stylesheet that makes `lg:hidden` actually hide
anything.

## Testing

- **Vitest + fake timers** (`tests/features/notifications/ws-client.test.ts`):
  `NotificationsSocket` against a fake `WebSocket` — connects with the right
  URL, ping→pong, forwards/ignores frames correctly, bounded exponential
  backoff (verified at each doubling step and the cap), attempt-counter
  reset on reopen, `onReconnected` firing only on a second open, and
  `disconnect()` both closing a live socket and cancelling a pending
  reconnect timer (no leak).
- **Vitest + RTL + MSW** (`tests/features/notifications/hooks.test.tsx`):
  `applyNotificationEvent`'s de-duplication (exactly-once rendering of an
  event already present from REST, and exactly-once badge-counting of a
  duplicate live redelivery even with no list cache to check against) and
  the mark-all/mark-selected mutations' cache fan-out and idempotency,
  against a bare `QueryClient`. Includes the regression test for the
  badge-doesn't-move-without-opening-the-panel bug above.
- **Vitest + RTL** (`tests/features/notifications/useNotificationsSocket.test.tsx`):
  the socket bridge's lifecycle — no connection while unauthenticated,
  connects with the current access token once authenticated, unmount
  disconnects (no leak), and logout disconnects + resets the store + clears
  the cached list.
- **Vitest + RTL + MSW + jest-axe**
  (`tests/features/notifications/NotificationsPanel.test.tsx`): loading/
  error/empty/populated states, unread-count display, mark-all/mark-selected
  read (including keyboard activation via Tab+Enter), "Load more" pagination,
  and an accessibility check.
- **Vitest + RTL + MSW** (`tests/routes/NotificationsInteractions.test.tsx`):
  `<App/>`-level — the `/notifications` route is reachable from the nav,
  and opening an unread row both marks it read and navigates to the tweet
  (like/reply) or profile (follow).
- **Vitest + RTL** (`tests/components/AppShell.test.tsx`): the nav item is
  hidden while unauthenticated and shows the unread badge once signed in.
- **Playwright, static build** (`frontend/e2e/notifications.spec.ts`):
  responsive (mobile/tablet/desktop) screenshots of the populated and empty
  panel plus the nav badge, and a "Mark all read" flow clearing the badge —
  saved to `frontend/test-results/screenshots/notifications-*.png`.

## Verification commands

```bash
cd frontend
npm run lint            # eslint . — clean (pre-existing App.tsx fast-refresh warning only)
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean (pre-existing e2e/feed.spec.ts,
                        # e2e/tweets.spec.ts warnings predate this task)
npm run test:coverage   # vitest run --coverage — 207 tests passed,
                        # 90.84% stmts / 85.19% branch / 88.20% funcs / 92.17% lines
npm run e2e             # npm run build && playwright test — 47 passed, incl.
                        # 7 new notifications screenshots/assertions
```

## Human review gate

Pending: notification placement (nav item position, panel layout), unread
behavior (badge priming/reset timing, what counts as "read" on open vs. on
explicit mark), and copy (verb text per notification type, empty/error
states, "Reconnecting…" banner).
