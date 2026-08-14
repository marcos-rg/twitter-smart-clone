# Reusable image-upload UI (TSC-MEDIA-002)

Frontend image picker/uploader, built directly on the `TSC-MEDIA-001` media
backend (`POST /api/v1/media/presign`, `POST /api/v1/media/confirm`,
`POST /api/v1/users/me/avatar`): presign → client `PUT`s straight to
MinIO/S3 → confirm. Built and validated in isolation in the `/lab`
component lab (`TSC-UX-001`) before being wired into the profile-edit
screen (`TSC-USER-002`).

## API layer

- [`frontend/src/api/media.ts`](../frontend/src/api/media.ts): `presignOne`,
  `confirmOne` (both single-file — see "why per-item" below),
  `putObjectWithProgress` (raw `XMLHttpRequest`, since `fetch` reports no
  upload progress), and `resolveMediaUrl(key)`, which turns a confirmed
  object key into a browser-loadable URL using
  `VITE_MEDIA_PUBLIC_BASE_URL` (defaults to
  `http://localhost:9000/twitter-smart-clone-media`, mirroring
  `MINIO_PUBLIC_ENDPOINT` + `MINIO_BUCKET`). Also exports the client-side
  validation constants (`ALLOWED_IMAGE_CONTENT_TYPES`, `MAX_IMAGE_BYTES`,
  `MAX_TWEET_IMAGES`), kept in sync with the backend's `Settings`/
  `ALLOWED_CONTENT_TYPES` defaults.
- [`frontend/src/api/users.ts`](../frontend/src/api/users.ts) gained
  `confirmMyAvatar(key)` → `POST /users/me/avatar`.
- New types in [`frontend/src/api/types.ts`](../frontend/src/api/types.ts):
  `MediaPurpose`, `PresignFileRequest`, `PresignedUpload`, `ConfirmedMedia`.

**Known limitation, not addressed here:** `Settings.minio_endpoint`
(`http://minio:9000`, the internal Docker hostname) is what the backend's S3
client actually signs presigned URLs against — `MINIO_PUBLIC_ENDPOINT` is
defined in `.env.example` but not wired into any backend setting. A real
browser outside the Compose network can't resolve `minio:9000`, so uploads
against a live `docker compose up` stack won't work end-to-end yet; that's a
`TSC-MEDIA-001`-side gap for a follow-up task, not something this frontend
task can fix by itself. All the verification below therefore exercises the
real request/response *shapes* over MSW rather than a live MinIO PUT (see
"Testing").

## `useImageUploader` — the reusable state machine

[`frontend/src/features/media/useImageUploader.ts`](../frontend/src/features/media/useImageUploader.ts)
owns everything both the avatar and tweet-image variants need:

- **Validation before any network call.** `addFiles` checks content-type and
  size client-side and never presigns a rejected file; reasons are exposed
  via `rejections: string[]` for the UI's `role="alert"` region — nothing is
  silently dropped.
- **Per-item, not batched, presign/upload/confirm.** Every selected file
  gets its own `presignOne` → `putObject` → `confirmOne` call, independent
  of every other item. This is what makes retry safe: retrying one failed
  item only re-runs *that* item's three calls — a succeeded sibling is never
  re-presigned, re-uploaded, or re-confirmed (covered directly by a test
  asserting exact call counts per filename across a retry).
- **Order.** Confirmed keys are derived from the `items` array (selection/
  reorder order), not from whichever upload happens to finish first, so
  `onConfirmedKeysChange` always reports the "approved order" a caller (a
  future tweet composer) should submit.
- **Object-URL lifecycle.** Every item's `previewUrl` is
  `URL.createObjectURL(file)`; it's revoked on `removeItem`, on replacement
  (single-file/avatar mode swaps files), and for every remaining item on
  unmount.
- **`MediaUploadAdapter` seam** (`presignOne`/`putObject`/`confirmOne`):
  `defaultMediaUploadAdapter` (real network) is enough for tweet images;
  `AvatarUploader` supplies its own, because confirming an avatar is a
  different endpoint (`POST /users/me/avatar`, not `/media/confirm`) that
  also has to update the cached signed-in user. A third,
  `createFakeMediaUploadAdapter` (deterministic timers, no network, fails
  any `fail-*`-named file), drives the `/lab` demo and the Playwright
  screenshot evidence.

## Components

- [`ImageUploader`](../frontend/src/features/media/ImageUploader.tsx):
  multi-image grid (`maxFiles` up to `MAX_TWEET_IMAGES`) — picker button,
  per-item progress bar, status text, retry/remove, keyboard-operable
  move-earlier/move-later reorder buttons (no drag-only affordance), and a
  per-image alt-text field. Built for tweet images; not wired into a
  composer yet (`TSC-TWEET-001`/`TSC-TWEET-002`).
- [`AvatarUploader`](../frontend/src/features/media/AvatarUploader.tsx):
  single-image variant wired into
  [`ProfileEditForm`](../frontend/src/features/users/ProfileEditForm.tsx).
  Uploads independently of the profile form's own Save button — selecting a
  new avatar image starts presign/upload/confirm immediately, and a
  successful confirm updates the auth store (`setSession`) and the cached
  profile query (`profileQueryKey`) directly, so the header/nav reflect the
  new avatar without waiting for (or requiring) a profile-form submit.
- [`ProfileHeader`](../frontend/src/features/users/ProfileHeader.tsx) now
  resolves `avatarKey` via `resolveMediaUrl` and passes it to `Avatar`
  (previously stubbed with `void avatarKey`, always showing initials).
- `/lab` gained an "Image uploader" section (both variants, fake adapter) —
  add a file named `fail-*` to see the partial-failure/retry state.

## Testing

- **Vitest + RTL + jest-axe, fake adapter**
  (`frontend/tests/features/media/useImageUploader.test.tsx`,
  `frontend/tests/features/media/ImageUploader.test.tsx`): confirmed-key
  ordering independent of upload-completion order, type/size/count rejection
  before any network call, retry-without-duplicating-successful-uploads
  (exact per-file call-count assertions), object-URL revocation on
  removal/replace/unmount, reorder, keyboard operability (`Tab`/`Enter` on
  the reorder controls), and zero `jest-axe` violations in the
  partial-failure state.
- **Vitest + RTL + MSW + jest-axe, real adapter**
  (`frontend/tests/routes/ProfileEditAvatar.test.tsx`): goes through the
  actual `AvatarUploader` adapter — `POST /media/presign`, a `PUT` to the
  (MSW-mocked) upload URL, `POST /users/me/avatar` — to prove the real
  request/response wiring, not just the fake-adapter UI logic. Covers the
  avatar showing immediately after upload (local preview) and, via a
  simulated session-restore with `avatar_key` already set, still showing
  after a "reload".
- **Playwright, static build** (`frontend/e2e/media-upload.spec.ts`): drives
  the `/lab` uploader (fake adapter, no backend — same convention as
  `lab.spec.ts`) through empty → uploading → partial-failure → complete,
  screenshotting each to `frontend/test-results/screenshots/`, plus a
  keyboard-operability check. `lab.spec.ts`'s existing three-breakpoint
  (375/768/1280px) no-overflow and reduced-motion checks now also cover the
  uploader section since it's part of the same page; `profile-search.spec.ts`
  covers the profile-edit screen (with `AvatarUploader`) at the same three
  breakpoints.

## Verification commands

```bash
cd frontend
npm run lint            # eslint . — clean
npm run typecheck       # tsc -b --noEmit — clean
npm run format:check    # prettier --check . — clean
npm run test:coverage   # vitest run --coverage — 125 tests passed,
                        # 89.93% stmts / 85.54% branch / 87.26% funcs / 91.22% lines
npm run e2e             # npm run build && playwright test — 22 passed, incl.
                        # media-upload empty/uploading/partial-failure/complete
                        # screenshots and profile-edit screenshots at 3 breakpoints
```

## Human review gate

Pending: preview/progress/retry/ordering UX (the per-item progress bar and
status text, retry vs. remove affordances, and the move-earlier/move-later
reorder controls for tweet images).
