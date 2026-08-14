# Twitter Smart Clone - Implementation Tasks

This document is the execution and progress tracker for the application defined in
[`requirements.md`](./requirements.md) and [`specification.md`](./specification.md).
It is written for AI coding agents and human reviewers. Tasks are intentionally sized
as reviewable increments rather than individual files or entire project phases.

## Task conventions

### Identifier and GitHub issue naming

- Stable task ID: `TSC-<AREA>-<NNN>`, for example `TSC-AUTH-001`.
- GitHub issue title: `[TSC-AUTH-001] Implement backend authentication`.
- IDs never change or get reused. New work receives a new ID even if an older task is
  cancelled or superseded.
- Commits and pull requests should reference the task ID. Dependencies use the same ID.

Area codes:

| Code | Area | Code | Area |
|---|---|---|---|
| `PLAN` | Scope and decisions | `FOUND` | Project foundation |
| `UX` | Design system and interaction lab | `CORE` | Backend platform |
| `DATA` | Database and seed data | `AUTH` | Authentication |
| `USER` | Profiles and search | `NOTIF` | Notifications |
| `SOC` | Follow graph | `MEDIA` | Image storage and upload |
| `TWEET` | Tweets and replies | `FEED` | Home feed |
| `LIKE` | Likes | `AI` | LLM features |
| `HARD` | Security, reliability, performance | `QA` | System verification |
| `OPS` | Delivery and deployment | `DOC` | User/developer documentation |
| `REL` | Release | | |

### Status values

- `To Do`: no implementation has been accepted.
- `In Progress`: active work exists, but every acceptance criterion is not yet satisfied.
- `Done`: all acceptance criteria pass, verification evidence is recorded in the issue or
  pull request, and every required human review gate is approved.

An agent must not mark a task `Done` based only on files existing. It must run the listed
verification, record the commands and results, and confirm that all dependencies are
`Done`. If a verification command changes during implementation, update this document
and the relevant living documentation in the same pull request.

### Current progress

| Status | Count |
|---|---:|
| Done | 27 |
| In Progress | 1 |
| To Do | 13 |

The counts above reflect the repository at the time this plan was created: requirements
and a draft specification exist, but scope sign-off and application implementation are
not complete.

## Execution order

Tasks may run in parallel only when their dependency lists permit it. The intended
human-review cadence is:

1. Approve scope and architecture.
2. Establish the runnable project, automated checks, and UI component lab.
3. Deliver each feature as backend, frontend, then integrated verification.
4. Perform whole-system security, performance, deployment, and release verification.

---

## Phase 0 - Scope and project foundation

<a id="tsc-plan-001"></a>
### TSC-PLAN-001 - Approve v1 scope and architecture decisions

- **Status:** Done
- **Objective / scope:** Reconcile the requirements and draft specification, approve the
  v1 boundaries, and record decisions that affect implementation. Resolve at least the
  tweet-deletion conflict, refresh-token family/reuse behavior, WebSocket token transport,
  avatar upload confirmation contract, LLM job contract, and local-versus-production
  object storage. Also decide whether a user's own tweets appear in their home feed. Tweet
  editing, nested replies, DMs, retweets, private accounts,
  moderation tools, password reset, and non-image media remain out of scope unless the
  specification is explicitly amended.
- **Dependencies:** None.
- **Expected outputs / artifacts:** Approved `requirements.md` and `specification.md`;
  architecture decision records under `docs/architecture/`; updated task dependencies if
  a decision changes sequencing.
- **AI-verifiable acceptance criteria:**
  - No contradictory in-scope/out-of-scope statements remain between the two source docs.
  - Every endpoint required by the approved v1 scope has an HTTP method, path, auth rule,
    request shape, success shape, and error behavior.
  - Decisions listed in the objective are explicitly documented and searchable.
  - The specification remains internally consistent with the task plan.
- **Verification / evidence:** Run link and terminology checks available in the repository;
  use targeted searches for `delete tweet`, `refresh token`, `WebSocket`, `avatar`,
  `job_id`, and `MinIO`; attach the resolved decision summary to the issue.
- **Human review gate:** Product/technical owner approves the v1 scope and ADRs.

<a id="tsc-found-001"></a>
### TSC-FOUND-001 - Scaffold the typed monorepo

- **Status:** Done
- **Objective / scope:** Create the backend and frontend structures from the specification,
  pin supported runtimes, and establish repeatable dependency management and code-quality
  commands. This task does not implement product features.
- **Dependencies:** [TSC-PLAN-001](#tsc-plan-001).
- **Expected outputs / artifacts:** `backend/` FastAPI/SQLModel project managed by `uv`;
  `frontend/` React 18/Vite/TypeScript project; lockfiles; Ruff, Black, mypy, ESLint,
  Prettier, TypeScript strict mode, Vitest, pytest, and Playwright configuration;
  repository editor/config files and an updated `.gitignore`.
- **AI-verifiable acceptance criteria:**
  - Clean dependency installs complete from lockfiles on a fresh checkout.
  - Backend and frontend each expose a minimal executable entry point.
  - Backend formatting/lint/type checks and frontend formatting/lint/type checks pass.
  - Placeholder unit tests run successfully in both projects.
  - No generated dependency directories, local environment files, or secrets are tracked.
- **Verification / evidence:** Record runtime versions and successful backend/frontend
  install, lint, type-check, and unit-test commands in the issue.
- **Human review gate:** Human confirms the repository structure and tool choices match the
  approved specification.

<a id="tsc-found-002"></a>
### TSC-FOUND-002 - Build the local container development stack

- **Status:** Done
- **Objective / scope:** Make local development reproducible with containers for the API,
  worker, frontend, PostgreSQL 16, Redis 7, and MinIO, including hot reload and persistent
  development volumes. Production hardening is deferred to `TSC-OPS-001`.
- **Dependencies:** [TSC-FOUND-001](#tsc-found-001).
- **Expected outputs / artifacts:** Backend and frontend development Dockerfiles;
  `docker-compose.yml`; `docker-compose.dev.yml`; `.env.example`; health checks; Makefile
  targets `up`, `down`, `lint`, `test`, `seed`, and `migrate`; setup documentation.
- **AI-verifiable acceptance criteria:**
  - A documented single command starts the full stack from a clean checkout.
  - Compose reports every required service healthy or ready within a documented timeout.
  - Frontend, API health endpoint, PostgreSQL, Redis, and MinIO are reachable from the
    expected containers without host-only assumptions.
  - `docker compose config` succeeds and no secret value is committed.
  - Stopping and restarting the stack preserves intended development data only.
- **Verification / evidence:** Save `docker compose config`, service status, API health
  response, frontend HTTP response, and Makefile smoke-command results.
- **Human review gate:** Human confirms one-command bring-up works on a clean machine.

<a id="tsc-found-003"></a>
### TSC-FOUND-003 - Establish baseline CI quality gates

- **Status:** Done
- **Objective / scope:** Add pull-request CI that runs the same containerized checks used
  locally. Establish the pipeline early so each later feature extends a working gate.
- **Dependencies:** [TSC-FOUND-001](#tsc-found-001),
  [TSC-FOUND-002](#tsc-found-002).
- **Expected outputs / artifacts:** GitHub Actions workflows for backend and frontend
  format/lint/type checks, tests, secret scanning, Compose integration smoke tests, and
  backend/frontend image builds; coverage reporting with ratcheting thresholds (raised as
  features land so the final 80%/70% gates in `TSC-QA-001` are not a cliff); documented
  local equivalents.
- **AI-verifiable acceptance criteria:**
  - Workflows trigger on pull requests and default-branch pushes with dependency caching.
  - Tests execute inside containers and do not call a real LLM provider.
  - Any lint, type, test, secret-scan, or image-build failure makes CI fail.
  - Workflow permissions are least-privilege and actions are version-pinned.
  - The complete baseline workflow passes on the current revision.
- **Verification / evidence:** Link a successful workflow run and record the equivalent
  local commands. Deliberately prove one gate fails on a temporary test branch or fixture.
  - Workflow: `.github/workflows/ci.yml` (jobs: `build-images`, `backend-quality`,
    `frontend-quality`, `secret-scan`, `compose-smoke`). Local equivalents, full local
    command output, and the deliberate-failure proofs (a fixture secret detected by
    gitleaks; an unformatted line rejected by `black --check`) are recorded in
    `docs/local-dev-stack.md` under "CI (`TSC-FOUND-003`)".
  - PR/workflow run link: opened from branch
    `11-tsc-found-003---establish-baseline-ci-quality-gates`; add the PR URL and the
    first green Actions run URL here once available from GitHub.
- **Human review gate:** Human reviews workflow permissions and required branch checks.

<a id="tsc-ux-001"></a>
### TSC-UX-001 - Create the design system and component interaction lab

- **Status:** Done
- **Objective / scope:** Define reusable visual tokens, responsive layouts, interaction
  patterns, and an isolated component showcase before feature pages multiply. Use an
  in-app development route or the already-approved component tool; do not add a second
  frontend framework solely for this task.
- **Dependencies:** [TSC-FOUND-001](#tsc-found-001),
  [TSC-PLAN-001](#tsc-plan-001).
- **Expected outputs / artifacts:** Tailwind theme/tokens; base typography and focus styles;
  accessible Button, Input, Textarea, Avatar, Modal, Toast, Skeleton, Tabs, TweetCard
  shell, empty/error states, responsive application shell; component lab route/tool;
  component tests and visual usage documentation.
- **AI-verifiable acceptance criteria:**
  - Components render representative default, loading, disabled, error, empty, and
    long-content states in isolation.
  - Keyboard navigation, visible focus, labels, and automated accessibility checks pass.
  - The lab renders at mobile, tablet, and desktop widths without horizontal overflow.
  - Motion respects `prefers-reduced-motion`.
  - Component tests and frontend quality checks pass.
- **Verification / evidence:** Record component-test and accessibility-check output and
  attach screenshots at the three required breakpoints.
- **Human review gate:** Human selects/approves visual direction and core interactions
  before feature pages are implemented.

<a id="tsc-core-001"></a>
### TSC-CORE-001 - Implement the backend application platform

- **Status:** Done
- **Objective / scope:** Build the shared FastAPI platform used by every feature: app
  factory, configuration, async resource lifecycle, API versioning, request IDs,
  structured logging, standard errors, security headers, and health/readiness checks.
  Product endpoints are out of scope.
- **Dependencies:** [TSC-FOUND-002](#tsc-found-002),
  [TSC-FOUND-003](#tsc-found-003).
- **Expected outputs / artifacts:** Typed settings using pydantic settings; async PostgreSQL, Redis, MinIO, and
  Celery wiring; `/healthz`, `/readyz`, `/api/v1/docs`, and `/api/v1/openapi.json`;
  RFC-9457-inspired error handlers; request-ID middleware; JSON log configuration;
  security-header middleware; environment-driven CORS configuration for the SPA origin;
  unit/integration tests and architecture docs.
- **AI-verifiable acceptance criteria:**
  - Liveness works without dependencies; readiness fails when a required dependency is
    unavailable and succeeds when all required dependencies are ready.
  - Every tested error uses the documented envelope and matching `X-Request-ID`.
  - Logs include request ID, method, path, status, and latency without secrets or tokens.
  - Cross-origin requests from the configured frontend origin succeed (including
    credentials for the refresh cookie) while unlisted origins are rejected.
  - Startup and shutdown cleanly acquire/release async resources.
  - Backend lint, type checks, platform tests, and OpenAPI generation pass.
- **Verification / evidence:** Record targeted pytest, lint, type-check, health/readiness,
  log-shape, and OpenAPI-generation results.
- **Human review gate:** Human reviews the layering and public error contract.

<a id="tsc-data-001"></a>
### TSC-DATA-001 - Implement schema, migrations, repositories, and seed data

- **Status:** Done
- **Objective / scope:** Implement the approved PostgreSQL data model, constraints,
  indexes, async repository foundations, migration lifecycle, and deterministic demo data.
- **Dependencies:** [TSC-CORE-001](#tsc-core-001),
  [TSC-PLAN-001](#tsc-plan-001).
- **Expected outputs / artifacts:** SQLModel models for users, tweets, tweet media, follows,
  likes, notifications, refresh tokens, and any approved AI job/token-family tables;
  Alembic configuration and initial migration; `citext` and `pg_trgm` extensions; typed
  repository base/pagination helpers; factories; idempotent seed CLI/script; schema docs.
- **AI-verifiable acceptance criteria:**
  - A clean database upgrades to head, downgrades as documented, and upgrades again.
  - Constraints reject duplicate usernames/emails, self-follows, duplicate follows/likes,
    invalid relationships, and other invariants assigned to the database.
  - Required unique, chronological, foreign-key, partial, and trigram indexes exist.
  - Seed runs twice without duplication or failure and creates useful demo relationships.
  - Repository and migration integration tests pass against real PostgreSQL.
- **Verification / evidence:** Record Alembic round-trip, schema/index inspection, seed
  counts, and targeted integration-test output.
- **Human review gate:** Human reviews the ER model, migration, and representative seed data.

---

## Phase 1 - Authentication vertical slice

<a id="tsc-auth-001"></a>
### TSC-AUTH-001 - Implement secure backend authentication

- **Status:** Done
- **Objective / scope:** Implement register, login, access-token validation, rotating
  refresh tokens with reuse response, logout, and current-user endpoints. Email/password
  is the only v1 login method.
- **Dependencies:** [TSC-DATA-001](#tsc-data-001),
  [TSC-CORE-001](#tsc-core-001).
- **Expected outputs / artifacts:** Auth schemas, repositories, services, dependencies, and
  routes; Argon2id hashing; JWT access tokens; hashed refresh-token persistence and family
  rotation/revocation; secure cookie configuration by environment; auth rate limits;
  unit/integration/security tests; OpenAPI examples.
- **AI-verifiable acceptance criteria:**
  - Register, login, refresh, logout, and `/auth/me` satisfy the approved API contract.
  - Passwords and raw refresh tokens never persist or appear in logs/responses.
  - Access tokens expire as configured; refresh rotation invalidates old tokens; detected
    reuse revokes the approved token family.
  - Duplicate/invalid credentials and missing/expired/revoked tokens return standard,
    non-enumerating errors.
  - Auth tests include cookie attributes, concurrency/replay cases, and rate limiting.
- **Verification / evidence:** Record targeted auth unit/integration tests, database checks
  for token hashes, cookie assertions, and OpenAPI contract output.
- **Human review gate:** Human reviews token lifetimes, cookie policy, and reuse behavior.

<a id="tsc-auth-002"></a>
### TSC-AUTH-002 - Implement frontend authentication and route protection

- **Status:** Done
- **Objective / scope:** Deliver register/login/logout/session restoration and protected
  routing while keeping access tokens in memory and refresh credentials in httpOnly
  cookies.
- **Dependencies:** [TSC-AUTH-001](#tsc-auth-001),
  [TSC-UX-001](#tsc-ux-001).
- **Expected outputs / artifacts:** Typed API client; auth query/mutation hooks; in-memory
  auth store; refresh serialization; register/login screens; protected/public route
  guards; logout; validation, feedback, loading, and expired-session states; MSW fixtures;
  component/integration tests.
- **AI-verifiable acceptance criteria:**
  - A user can register, authenticate, reload, restore a valid session, and log out.
  - Access tokens are absent from localStorage, sessionStorage, IndexedDB, and readable
    cookies.
  - Concurrent `401` responses cause at most one refresh attempt and retry only once.
  - Failed refresh clears auth state and redirects to login without a redirect loop.
  - Forms are keyboard accessible and frontend tests/type checks pass.
- **Verification / evidence:** Record targeted Vitest/RTL/MSW tests and browser-storage
  inspection; attach mobile and desktop auth-screen screenshots.
- **Human review gate:** Human approves auth copy, validation feedback, and redirect UX.

<a id="tsc-auth-003"></a>
### TSC-AUTH-003 - Verify the authentication vertical slice

- **Status:** Done
- **Objective / scope:** Prove backend and frontend auth work together in the container
  stack, including failure and recovery paths.
- **Dependencies:** [TSC-AUTH-001](#tsc-auth-001),
  [TSC-AUTH-002](#tsc-auth-002),
  [TSC-FOUND-002](#tsc-found-002).
- **Expected outputs / artifacts:** Playwright auth suite; API contract tests; auth threat
  checklist; CI integration; captured run evidence.
- **AI-verifiable acceptance criteria:**
  - E2E covers register, login, protected navigation, reload/refresh, logout, invalid
    credentials, expired access token recovery, revoked refresh token, and duplicate user.
  - Tests run in containers against real PostgreSQL and Redis.
  - No browser console error, unhandled request, secret disclosure, or flaky retry remains.
  - The auth E2E suite passes three consecutive times.
- **Verification / evidence:** Record three consecutive targeted E2E runs plus backend and
  frontend auth suites in CI.
- **Human review gate:** Human completes a manual auth smoke test and approves the slice.

---

## Phase 2 - Profiles, search, and social graph

<a id="tsc-user-001"></a>
### TSC-USER-001 - Implement profile and user-search backend

- **Status:** Done
- **Objective / scope:** Implement public profiles, self-editing, profile timelines contract,
  and exact/prefix/fuzzy user search with object-level authorization.
- **Dependencies:** [TSC-AUTH-003](#tsc-auth-003),
  [TSC-DATA-001](#tsc-data-001).
- **Expected outputs / artifacts:** Profile/search schemas, repository queries, services,
  routes, opaque cursor helpers, validators, OpenAPI examples, and unit/integration tests.
  Avatar binary upload is handled by `TSC-MEDIA-001`.
- **AI-verifiable acceptance criteria:**
  - Public profile lookup is case-insensitive by username and excludes private fields.
  - Only the current user can edit their profile; uniqueness conflicts are deterministic.
  - Username, email, name, and 160-character bio validation match the specification.
  - Exact, prefix, and fuzzy search return correctly ordered, cursor-paginated results and
    use the intended indexes under representative data.
  - Unauthorized update attempts and malformed cursors return standard errors.
- **Verification / evidence:** Record targeted API tests and representative PostgreSQL
  `EXPLAIN` evidence for the three search modes.
- **Human review gate:** Human reviews public/private field boundaries and search relevance.

<a id="tsc-user-002"></a>
### TSC-USER-002 - Implement profile, profile-edit, and search interfaces

- **Status:** Done
- **Objective / scope:** Build responsive own/other profile pages, editable profile fields,
  user search with mode selection, and stable loading/error/empty states.
- **Dependencies:** [TSC-USER-001](#tsc-user-001),
  [TSC-UX-001](#tsc-ux-001),
  [TSC-AUTH-002](#tsc-auth-002).
- **Expected outputs / artifacts:** Profile and edit routes; profile header; safe field
  rendering; search screen with exact/prefix/fuzzy modes and debouncing; query hooks;
  cursor loading; MSW fixtures; component/integration tests.
- **AI-verifiable acceptance criteria:**
  - Own and other-user profiles render the correct controls and never expose email on a
    public profile unless the approved contract says otherwise.
  - Edit validation mirrors the backend and conflicts preserve user-entered values.
  - Search mode, query, loading, no-results, pagination, and error states are test-covered.
  - Rapid queries do not display stale results from an older request.
  - Pages pass keyboard, accessibility, and three-breakpoint overflow checks.
- **Verification / evidence:** Record targeted frontend tests and accessibility output;
  attach profile/search screenshots at required breakpoints.
- **Human review gate:** Human approves profile information hierarchy and search behavior.

<a id="tsc-user-003"></a>
### TSC-USER-003 - Verify profiles and search end to end

- **Status:** Done
- **Objective / scope:** Validate profile viewing/editing and all search modes against the
  real API and database.
- **Dependencies:** [TSC-USER-001](#tsc-user-001),
  [TSC-USER-002](#tsc-user-002).
- **Expected outputs / artifacts:** Playwright profile/search scenarios; query-plan fixture
  dataset; authorization regression tests; CI evidence.
- **AI-verifiable acceptance criteria:**
  - E2E covers own/other profile, valid edit, uniqueness conflict, unauthorized edit,
    exact/prefix/fuzzy search, no results, and multi-page search results.
  - Seeded misspellings produce the approved fuzzy-search matches and ordering.
  - Browser and API results agree for the same query/cursor.
  - Targeted E2E passes three consecutive times without console or request errors.
- **Verification / evidence:** Record three targeted E2E runs and backend query-plan tests.
- **Human review gate:** Human validates search relevance using the seeded dataset.

<a id="tsc-notif-001"></a>
### TSC-NOTIF-001 - Build notification persistence and delivery APIs

- **Status:** Done
- **Objective / scope:** Build the reusable notification resource before social actions
  depend on it: transactional persistence, list/read APIs, and post-commit Redis
  publication of the event envelope. Trigger wiring is completed by follow, reply, and
  like tasks; live WebSocket delivery is completed by `TSC-NOTIF-004`.
- **Dependencies:** [TSC-USER-001](#tsc-user-001),
  [TSC-CORE-001](#tsc-core-001).
- **Expected outputs / artifacts:** Notification repository/service/routes; cursor pagination;
  mark-selected/mark-all-read behavior; post-commit Redis publisher; documented event
  envelope with stable notification IDs; unit/integration tests and contract documentation.
- **AI-verifiable acceptance criteria:**
  - Notification rows commit before publication and failed transactions publish nothing.
  - A recipient can list/read only their own notifications; unread state is accurate.
  - Published events follow the documented envelope and carry stable notification IDs
    that clients can use to de-duplicate.
  - List pagination is cursor-stable and malformed cursors return standard errors.
  - Mark-selected and mark-all-read update unread state exactly once and are idempotent.
- **Verification / evidence:** Record API, transaction, pagination, authorization, and
  Redis-publish test output.
- **Human review gate:** Human reviews the notification contract and event envelope.

<a id="tsc-notif-004"></a>
### TSC-NOTIF-004 - Build authenticated realtime WebSocket infrastructure

- **Status:** Done
- **Objective / scope:** Deliver the realtime transport that pushes persisted notification
  events to online clients: authenticated WebSocket endpoint, connection lifecycle,
  heartbeat, Redis subscriber bridge, and multi-worker routing. The notification resource
  itself is owned by `TSC-NOTIF-001`.
- **Dependencies:** [TSC-NOTIF-001](#tsc-notif-001),
  [TSC-AUTH-001](#tsc-auth-001),
  [TSC-CORE-001](#tsc-core-001).
- **Expected outputs / artifacts:** WebSocket endpoint with token validation on connect;
  in-process connection manager keyed by user with multi-connection support; Redis
  subscriber bridge; heartbeat/reaping; documented reconnect contract; WS integration
  tests and protocol documentation.
- **AI-verifiable acceptance criteria:**
  - Invalid/expired WebSocket credentials are rejected without entering the registry.
  - Multiple tabs receive a notification once per connection; reconnects do not leak
    subscriptions, sockets, or Redis channels.
  - An event published by one API process reaches a socket held by another process.
  - Idle or broken sockets are detected by heartbeat and reaped within the documented
    interval.
  - A persisted event published while the recipient is connected is delivered within the
    2-second budget in the test environment.
- **Verification / evidence:** Record multi-process WS, auth-rejection, heartbeat,
  reconnect, and latency test output.
- **Human review gate:** Human reviews the WebSocket auth and reconnect protocol.

<a id="tsc-soc-001"></a>
### TSC-SOC-001 - Implement follow graph backend

- **Status:** Done
- **Objective / scope:** Implement idempotent follow/unfollow behavior, follower/following
  lists, counts, and follow notifications.
- **Dependencies:** [TSC-USER-001](#tsc-user-001),
  [TSC-NOTIF-001](#tsc-notif-001).
- **Expected outputs / artifacts:** Follow repository/service/routes; paginated follower and
  following responses; profile relationship/count fields; transactional follow
  notification creation; rate-limit integration; unit/integration/concurrency tests.
- **AI-verifiable acceptance criteria:**
  - Users cannot follow themselves; duplicate follow/unfollow calls have documented,
    deterministic idempotent behavior.
  - Follow state and counts remain correct under concurrent requests.
  - A new follow creates exactly one persisted notification after commit; unfollow creates
    none; self-notifications are impossible.
  - Follower/following lists are stable and cursor-paginated without duplicates.
  - Authorization, standard errors, and configured rate limits are test-covered.
- **Verification / evidence:** Record targeted service/API/concurrency tests and database
  count checks.
- **Human review gate:** Human reviews idempotency behavior and public social-graph fields.

<a id="tsc-soc-002"></a>
### TSC-SOC-002 - Implement follow and social-list interfaces

- **Status:** Done
- **Objective / scope:** Add follow/unfollow controls and follower/following lists with
  optimistic updates and rollback.
- **Dependencies:** [TSC-SOC-001](#tsc-soc-001),
  [TSC-USER-002](#tsc-user-002).
- **Expected outputs / artifacts:** Follow button/state; follower/following tabs or routes;
  paginated user lists; optimistic TanStack Query mutations; rollback/toast behavior;
  accessible confirmation/error states; tests and MSW scenarios.
- **AI-verifiable acceptance criteria:**
  - Correct controls render for self, followed, and unfollowed profiles.
  - Optimistic state updates all relevant counts/lists and fully rolls back on failure.
  - Repeated rapid clicks cannot issue contradictory concurrent mutations.
  - Paginated lists do not duplicate users and preserve state after navigation.
  - Component/integration/accessibility tests pass at all breakpoints.
- **Verification / evidence:** Record targeted frontend tests, including forced API failure
  and rapid-click cases; attach responsive screenshots.
- **Human review gate:** Human approves optimistic interaction and list navigation.

<a id="tsc-soc-003"></a>
### TSC-SOC-003 - Verify the social graph vertical slice

- **Status:** Done
- **Objective / scope:** Prove follow/unfollow, lists, counts, and persisted/live follow
  notifications work together.
- **Dependencies:** [TSC-SOC-001](#tsc-soc-001),
  [TSC-SOC-002](#tsc-soc-002),
  [TSC-NOTIF-004](#tsc-notif-004).
- **Expected outputs / artifacts:** Multi-user Playwright scenarios; API/database invariant
  checks; realtime follow-notification test; CI evidence.
- **AI-verifiable acceptance criteria:**
  - E2E covers follow, duplicate attempt, follower/following lists, unfollow, optimistic
    rollback, self-follow rejection, and offline notification persistence.
  - Online follow notification arrives within 2 seconds in the test environment.
  - UI counts, API counts, and database relationships agree after each action.
  - Targeted E2E passes three consecutive times.
- **Verification / evidence:** Record three E2E runs, notification latency measurements,
  and invariant-query results.
- **Human review gate:** Human completes a two-user follow/unfollow smoke test.

---

## Phase 3 - Media, tweets, replies, and timelines

<a id="tsc-media-001"></a>
### TSC-MEDIA-001 - Implement secure media upload backend

- **Status:** Done
- **Objective / scope:** Implement direct-to-S3/MinIO image uploads for tweet images and
  avatars using presigned URLs and server-side object confirmation.
- **Dependencies:** [TSC-AUTH-003](#tsc-auth-003),
  [TSC-CORE-001](#tsc-core-001),
  [TSC-DATA-001](#tsc-data-001).
- **Expected outputs / artifacts:** Storage abstraction; presign and approved avatar
  confirmation endpoints that persist the confirmed avatar key; randomized user-scoped
  object keys; object existence/metadata
  verification; content-type, size, count, and ownership validation; cleanup policy/task
  for abandoned uploads; tests with MinIO and mocked storage failures; upload-flow docs.
- **AI-verifiable acceptance criteria:**
  - PNG, JPEG, and WebP files within limits can be presigned, uploaded, and confirmed.
  - Confirming an owned avatar updates the authenticated user's profile, and the value
    remains present after a fresh profile read.
  - Unsupported types, oversized files, more than four tweet images, missing objects,
    altered metadata, and keys owned by another user are rejected.
  - API containers never proxy image bytes during the normal upload flow.
  - Presigned URLs expire and object keys prevent path traversal/guessable overwrites.
  - Storage integration and failure-path tests pass against MinIO.
- **Verification / evidence:** Record targeted tests, example object metadata, expiry check,
  and proof that the API request body does not carry image bytes.
- **Human review gate:** Human reviews upload limits and abandoned-upload behavior.

<a id="tsc-media-002"></a>
### TSC-MEDIA-002 - Build and validate reusable image-upload UI

- **Status:** Done
- **Objective / scope:** Build an isolated avatar/tweet image picker and uploader before
  embedding it in final composer/profile screens.
- **Dependencies:** [TSC-MEDIA-001](#tsc-media-001),
  [TSC-UX-001](#tsc-ux-001),
  [TSC-AUTH-002](#tsc-auth-002),
  [TSC-USER-002](#tsc-user-002).
- **Expected outputs / artifacts:** Reusable image picker, preview grid, progress, retry,
  remove/reorder, alt-label strategy, client-side validation, object URL cleanup, component
  lab examples, MSW/MinIO integration tests, and UX documentation.
- **AI-verifiable acceptance criteria:**
  - Valid files upload and produce confirmed keys in the approved order.
  - The avatar variant is integrated into profile edit and displays the confirmed avatar
    after save and reload.
  - Invalid type/size/count is rejected before upload with accessible feedback.
  - Partial upload failure supports retry/removal without duplicating successful uploads.
  - Temporary object URLs are revoked when replaced or unmounted.
  - Keyboard use, reduced motion, and mobile/desktop layout tests pass.
- **Verification / evidence:** Record component/integration tests and attach screenshots of
  empty, uploading, partial-failure, and complete states.
- **Human review gate:** Human selects/approves preview, progress, retry, and ordering UX.

<a id="tsc-tweet-001"></a>
### TSC-TWEET-001 - Implement tweet, reply, and profile-timeline backend

- **Status:** Done
- **Objective / scope:** Implement tweet creation/retrieval, safe text/link data, up to four
  confirmed images, flat replies, reply counters, replies listing, and user timelines.
  Tweet editing/deletion and nested replies are excluded.
- **Dependencies:** [TSC-MEDIA-001](#tsc-media-001),
  [TSC-NOTIF-001](#tsc-notif-001),
  [TSC-DATA-001](#tsc-data-001),
  [TSC-USER-001](#tsc-user-001).
- **Expected outputs / artifacts:** Tweet/media schemas, repositories, services, routes;
  create/get/replies/user-timeline cursor pagination; reply transaction and notification;
  image ordering and safe-link contract; unit/integration/concurrency tests; OpenAPI.
- **AI-verifiable acceptance criteria:**
  - Tweet content accepts 1-280 characters under the approved whitespace policy and no
    more than four confirmed images owned by the author.
  - Replies can target root tweets only; attempts to reply to replies are rejected.
  - Reply insert, counter increment, and notification persistence are atomic and remain
    correct under concurrent requests.
  - Tweet/reply/profile timeline cursors are stable with identical timestamps and no
    duplicate or skipped records across pages.
  - Responses include author, viewer state, counts, ordered media, and safely renderable
    link data without trusting client user IDs.
- **Verification / evidence:** Record targeted validator, transaction, concurrency,
  pagination, authorization, and API contract tests.
- **Human review gate:** Human reviews whitespace/link behavior and flat-reply semantics.

<a id="tsc-tweet-002"></a>
### TSC-TWEET-002 - Implement tweet composer, cards, detail, replies, and timelines

- **Status:** Done
- **Objective / scope:** Build the primary tweet UI using approved components and media
  upload, including profile timelines and tweet detail with flat replies.
- **Dependencies:** [TSC-TWEET-001](#tsc-tweet-001),
  [TSC-MEDIA-002](#tsc-media-002),
  [TSC-USER-002](#tsc-user-002).
- **Expected outputs / artifacts:** Tweet composer with character counter; safe linkified
  content; image gallery; TweetCard; profile timeline; tweet detail; reply composer/list;
  cursor hooks; skeleton/empty/error states; cache updates; tests and MSW fixtures.
- **AI-verifiable acceptance criteria:**
  - Composer enforces the backend length/whitespace/media rules and preserves input after
    recoverable failures.
  - User text is React-escaped, generated links use safe protocols/attributes, and no user
    content is passed to `dangerouslySetInnerHTML`.
  - Successful tweets/replies update relevant caches and counters without full reload.
  - Nested reply controls are absent and direct nested-reply URLs fail safely.
  - Long text, four images, missing avatar, pagination, and all standard states pass
    responsive, accessibility, and component tests.
- **Verification / evidence:** Record targeted frontend/security tests and screenshots for
  composer, card, detail, reply, and profile timeline at required breakpoints.
- **Human review gate:** Human approves composer, media gallery, link, and reply UX.

<a id="tsc-tweet-003"></a>
### TSC-TWEET-003 - Verify tweets and replies end to end

- **Status:** Done
- **Objective / scope:** Prove text/image/link tweets, timelines, flat replies, counters, and
  reply notifications across the real stack.
- **Dependencies:** [TSC-TWEET-001](#tsc-tweet-001),
  [TSC-TWEET-002](#tsc-tweet-002),
  [TSC-NOTIF-004](#tsc-notif-004).
- **Expected outputs / artifacts:** Playwright tweet/reply/media suite; pagination and
  transaction invariant checks; CI artifacts including failure traces/screenshots.
- **AI-verifiable acceptance criteria:**
  - E2E covers text, link, 1-image, 4-image, invalid/oversized media, profile timeline,
    detail, reply, nested-reply rejection, upload failure/retry, and offline persistence.
  - Online reply notification arrives within 2 seconds.
  - UI counts, API counts, database counters, and object ordering agree.
  - Targeted E2E passes three consecutive times without leaked test objects.
- **Verification / evidence:** Record three E2E runs, latency, database invariants, and
  MinIO cleanup/object checks.
- **Human review gate:** Human completes a tweet-with-media and reply journey.

---

## Phase 4 - Feed and likes

<a id="tsc-feed-001"></a>
### TSC-FEED-001 - Implement chronological home-feed backend

- **Status:** Done
- **Objective / scope:** Implement fan-out-on-read feed retrieval from followed users using
  stable keyset pagination and an optional short-TTL first-page Redis cache.
- **Dependencies:** [TSC-TWEET-001](#tsc-tweet-001),
  [TSC-SOC-001](#tsc-soc-001).
- **Expected outputs / artifacts:** Feed repository query/service/route; opaque cursor
  codec; deterministic tie-breaking; first-page cache with invalidation/TTL policy if
  retained; query-plan tests; integration/concurrency tests; OpenAPI examples.
- **AI-verifiable acceptance criteria:**
  - Feed contains only approved authors (followed users and current user only if the
    approved product rule includes self), newest first.
  - Identical timestamps and concurrent inserts cause no duplicate/skip within the
    documented snapshot/keyset semantics.
  - Limits default to 20, reject values above 50, and malformed cursors use standard errors.
  - Representative query plans use intended indexes and avoid per-tweet N+1 queries.
  - Cache never exposes one user's feed to another and expires/invalidates as documented.
- **Verification / evidence:** Record pagination/insertion tests, SQL statement counts,
  `EXPLAIN` output, and cache isolation/expiry results.
- **Human review gate:** Human approves whether own tweets appear and the refresh semantics.

<a id="tsc-feed-002"></a>
### TSC-FEED-002 - Implement responsive infinite-scrolling home feed

- **Status:** Done
- **Objective / scope:** Build the authenticated home route, infinite scrolling, refresh,
  and resilient feed states using the shared TweetCard.
- **Dependencies:** [TSC-FEED-001](#tsc-feed-001),
  [TSC-TWEET-002](#tsc-tweet-002).
- **Expected outputs / artifacts:** Feed route; infinite-query hook; IntersectionObserver
  pagination; refresh/new-post behavior; skeleton, empty, end, retry, and offline/error
  states; scroll restoration policy; tests and MSW fixtures.
- **AI-verifiable acceptance criteria:**
  - Each next cursor is requested at most once per trigger and items are de-duplicated by ID.
  - Loading, retry, empty, end-of-feed, refresh, and newly-created-tweet states are covered.
  - Navigating to detail and back follows the approved scroll-restoration behavior.
  - Observer cleanup prevents requests after unmount.
  - Feed passes accessibility and overflow tests at all required breakpoints.
- **Verification / evidence:** Record targeted hook/component tests and responsive
  screenshots with multi-page seeded data.
- **Human review gate:** Human approves loading, refresh, empty-feed, and scroll behavior.

<a id="tsc-feed-003"></a>
### TSC-FEED-003 - Verify feed behavior end to end

- **Status:** Done
- **Objective / scope:** Validate feed membership, ordering, pagination, new-post behavior,
  and responsive interaction against the real stack.
- **Dependencies:** [TSC-FEED-001](#tsc-feed-001),
  [TSC-FEED-002](#tsc-feed-002).
- **Expected outputs / artifacts:** Multi-user Playwright feed scenarios; deterministic
  timestamp fixtures; API/UI ordering assertions; CI evidence.
- **AI-verifiable acceptance criteria:**
  - E2E proves followed tweets appear, unfollowed/unrelated tweets do not, and ordering is
    deterministic across at least three pages.
  - Follow/unfollow and new tweet actions produce the approved feed change after refresh.
  - No duplicate/skip occurs in the controlled concurrent-insert scenario.
  - Targeted E2E passes three consecutive times at mobile and desktop viewports.
- **Verification / evidence:** Record three E2E runs and API/UI ordered-ID comparisons.
- **Human review gate:** Human performs a seeded feed relevance and navigation smoke test.

<a id="tsc-like-001"></a>
### TSC-LIKE-001 - Implement like/unlike backend

- **Status:** Done
- **Objective / scope:** Implement idempotent likes, accurate counters, viewer-like state,
  notifications, and rate limiting.
- **Dependencies:** [TSC-TWEET-001](#tsc-tweet-001),
  [TSC-NOTIF-001](#tsc-notif-001).
- **Expected outputs / artifacts:** Like repository/service/routes; transactional counter and
  notification behavior; tweet response integration; periodic counter reconciliation task;
  unit/integration/concurrency tests.
- **AI-verifiable acceptance criteria:**
  - Like/unlike idempotency follows the approved contract and counters never go negative.
  - Like row, counter update, and new-like notification commit atomically.
  - Duplicate likes create no duplicate notification; self-like notification behavior
    matches the approved decision.
  - Concurrent like/unlike tests leave database rows and counters consistent.
  - Reconciliation detects and repairs deliberately introduced counter drift.
- **Verification / evidence:** Record transaction/concurrency/idempotency/reconciliation
  test output and database invariants.
- **Human review gate:** Human reviews idempotency and self-notification behavior.

<a id="tsc-like-002"></a>
### TSC-LIKE-002 - Implement optimistic like interactions

- **Status:** In Progress
- **Objective / scope:** Add accessible like/unlike controls to tweet cards and details with
  optimistic count/state updates, animation, and reliable rollback.
- **Dependencies:** [TSC-LIKE-001](#tsc-like-001),
  [TSC-TWEET-002](#tsc-tweet-002).
- **Expected outputs / artifacts:** Like mutation hooks; shared optimistic cache updater;
  disabled/pending behavior; rollback and toast feedback; reduced-motion animation;
  component/integration tests.
- **AI-verifiable acceptance criteria:**
  - Like state/count updates consistently across every cached representation of a tweet.
  - Failed mutations restore the exact prior state and display an accessible error.
  - Rapid clicks cannot produce negative counts or contradictory requests.
  - Animation is subtle and disabled under reduced-motion preference.
  - Tests cover success, idempotent response, failure rollback, stale cache, and rapid input.
- **Verification / evidence:** Record targeted frontend tests and component-lab captures for
  liked, unliked, pending, failed, and reduced-motion states.
- **Human review gate:** Human approves like feedback and animation.

<a id="tsc-like-003"></a>
### TSC-LIKE-003 - Verify likes end to end

- **Status:** To Do
- **Objective / scope:** Prove likes, counters, optimistic behavior, persistence, and live/
  offline notifications work together.
- **Dependencies:** [TSC-LIKE-001](#tsc-like-001),
  [TSC-LIKE-002](#tsc-like-002),
  [TSC-NOTIF-004](#tsc-notif-004).
- **Expected outputs / artifacts:** Two-user Playwright like scenarios; counter invariant and
  notification latency checks; CI evidence.
- **AI-verifiable acceptance criteria:**
  - E2E covers like, duplicate attempt, unlike, forced rollback, reload persistence, and
    online/offline recipient behavior.
  - Online like notification arrives within 2 seconds and exactly one persisted record
    exists for the triggering like.
  - UI, API, and database counts agree after each operation.
  - Targeted E2E passes three consecutive times.
- **Verification / evidence:** Record three E2E runs, latency measurements, and invariant
  query output.
- **Human review gate:** Human performs a two-user like/unlike smoke test.

---

## Phase 5 - Notifications experience

<a id="tsc-notif-002"></a>
### TSC-NOTIF-002 - Implement realtime notifications interface

- **Status:** To Do
- **Objective / scope:** Build the notification panel/page, unread badge, authenticated
  WebSocket client, reconnect/backoff/heartbeat behavior, de-duplication, and cache updates.
- **Dependencies:** [TSC-NOTIF-001](#tsc-notif-001),
  [TSC-NOTIF-004](#tsc-notif-004),
  [TSC-SOC-002](#tsc-soc-002),
  [TSC-TWEET-002](#tsc-tweet-002),
  [TSC-LIKE-002](#tsc-like-002).
- **Expected outputs / artifacts:** Notification query/mutation hooks; normalized store;
  WebSocket client; unread badge; list/panel; mark-selected/all-read; reconnect state;
  event-driven cache patching; tests with mocked REST/WS events.
- **AI-verifiable acceptance criteria:**
  - Follow, like, and reply events render once even when also returned by REST.
  - Events update unread count and relevant tweet/profile caches without a full reload.
  - Disconnect uses bounded exponential backoff; reconnect restores state from persisted
    notifications and does not leak sockets or timers.
  - Logout closes the socket and clears user-specific notification state.
  - List pagination, read actions, keyboard behavior, and all states pass frontend tests.
- **Verification / evidence:** Record hook/store/component tests including duplicate events,
  reconnect, logout, and timer cleanup; attach responsive screenshots.
- **Human review gate:** Human approves notification placement, unread behavior, and copy.

<a id="tsc-notif-003"></a>
### TSC-NOTIF-003 - Verify realtime and offline notifications

- **Status:** To Do
- **Objective / scope:** Validate notification persistence, delivery, de-duplication,
  authorization, reconnection, and cross-worker operation for every event type.
- **Dependencies:** [TSC-NOTIF-002](#tsc-notif-002),
  [TSC-SOC-003](#tsc-soc-003),
  [TSC-TWEET-003](#tsc-tweet-003),
  [TSC-LIKE-003](#tsc-like-003).
- **Expected outputs / artifacts:** Multi-browser Playwright suite; cross-worker integration
  test; latency report; disconnect/reconnect/offline scenarios; authorization tests.
- **AI-verifiable acceptance criteria:**
  - Follow, like, and reply each arrive online within 2 seconds in at least 95 of 100 local
    measured events, with no event exceeding the documented test timeout.
  - Offline events appear once after reconnect/fetch and can be marked read.
  - Duplicate Redis delivery and REST/WS races render one item by notification ID.
  - A user cannot subscribe to, list, or mark another user's notifications.
  - Multi-worker, multiple-tab, heartbeat timeout, token expiry, reconnect, and logout pass.
- **Verification / evidence:** Attach machine-readable latency results and targeted API, WS,
  and Playwright output from three consecutive runs.
- **Human review gate:** Human observes online and offline notification journeys.

---

## Phase 6 - LLM features

<a id="tsc-ai-001"></a>
### TSC-AI-001 - Implement provider-agnostic asynchronous AI backend

- **Status:** To Do
- **Objective / scope:** Implement queued tweet generation and thread summarization through a
  provider abstraction, with polling and optional WebSocket completion, safety controls,
  budget/rate limits, and no real-provider use in automated tests.
- **Dependencies:** [TSC-TWEET-003](#tsc-tweet-003),
  [TSC-NOTIF-004](#tsc-notif-004).
- **Expected outputs / artifacts:** Provider interface/adapters; versioned LangChain prompt
  templates; Celery jobs; persisted job state; generate/summarize/job-status routes;
  timeouts and bounded retries; moderation, prompt-injection boundaries, output validation,
  token-usage metadata, daily/global caps; fake provider; tests and AI operations docs.
- **AI-verifiable acceptance criteria:**
  - Submit endpoints return `202` and a job ID without waiting for provider completion.
  - `GET /ai/jobs/{job_id}` returns documented queued, running, succeeded, refused, and
    failed states, returns the validated result only at success, and rejects other users.
  - Only the job owner can poll/receive results; thread input is limited to authorized
    root tweet plus flat replies.
  - Tweet output is at most 280 characters; summaries and prompts obey approved limits.
  - Tweet content is passed as untrusted delimited data, not inserted into system
    instructions; provider output cannot trigger tools or application actions.
  - Timeout, retry exhaustion, moderation refusal, cap reached, provider failure, and
    worker restart produce durable, user-safe terminal states.
  - Successful completion is available through polling and is published as one
    authenticated WebSocket completion event with the same job ID.
  - Tests are deterministic with a fake provider and make zero billable network calls.
- **Verification / evidence:** Record targeted service/worker/API/security tests, job-state
  transitions, and network-denial proof for the test suite.
- **Human review gate:** Human approves prompts, refusal copy, limits, provider config, and
  cost controls.

<a id="tsc-ai-002"></a>
### TSC-AI-002 - Implement tweet-generation and thread-summary interfaces

- **Status:** To Do
- **Objective / scope:** Add optional AI assistance to the tweet composer and tweet detail
  without auto-posting generated content or obscuring failures.
- **Dependencies:** [TSC-AI-001](#tsc-ai-001),
  [TSC-TWEET-002](#tsc-tweet-002),
  [TSC-NOTIF-002](#tsc-notif-002).
- **Expected outputs / artifacts:** Generate-draft prompt UI; editable draft insertion;
  summarize-thread action/result; job polling/event hook; queued, running, success,
  refusal, limit, retry, and failure states; tests and component-lab examples.
- **AI-verifiable acceptance criteria:**
  - Generated text is never posted until the user explicitly edits/accepts and submits it.
  - Existing composer text is not destroyed without confirmation under the approved UX.
  - Polling stops on terminal state/unmount and does not duplicate WebSocket completion.
  - Polling renders every documented job state and cannot retrieve another user's job.
  - Summary clearly identifies the source thread and handles zero/many replies.
  - Loading, refusal, timeout, cap, provider error, retry, and accessibility tests pass.
- **Verification / evidence:** Record frontend tests for every job state and attach approved
  mobile/desktop interaction captures.
- **Human review gate:** Human approves disclosure, draft replacement, summary, and failure UX.

<a id="tsc-ai-003"></a>
### TSC-AI-003 - Verify AI features end to end

- **Status:** To Do
- **Objective / scope:** Validate asynchronous AI flows, authorization, guardrails, and
  recovery across API, worker, Redis, database, WebSocket/polling, and frontend.
- **Dependencies:** [TSC-AI-001](#tsc-ai-001),
  [TSC-AI-002](#tsc-ai-002).
- **Expected outputs / artifacts:** Fake-provider E2E scenarios; worker restart/retry tests;
  prompt-injection and moderation regression corpus; no-spend CI guard; evidence.
- **AI-verifiable acceptance criteria:**
  - E2E covers generation, user edit before post, summary, polling completion, WS completion,
    refusal, rate/daily cap, timeout/retry, provider failure, and worker restart.
  - Malicious instructions inside tweet text do not alter the system task or expose secrets.
  - Cross-user job/thread access is rejected.
  - CI proves no request reaches a real provider host.
  - Targeted E2E passes three consecutive times.
- **Verification / evidence:** Record three E2E runs, guardrail corpus results, worker
  recovery output, and denied-network logs.
- **Human review gate:** Human reviews representative generated/refused/failed experiences.

---

## Phase 7 - Hardening, operations, and release

<a id="tsc-hard-001"></a>
### TSC-HARD-001 - Complete security and abuse-resistance hardening

- **Status:** To Do
- **Objective / scope:** Audit and close cross-cutting security gaps after feature surfaces
  exist: authentication/authorization, validation, rate limits, headers, CORS/CSRF, XSS,
  SQL injection resistance, secrets, upload safety, logs, and dependency vulnerabilities.
- **Dependencies:** [TSC-AUTH-003](#tsc-auth-003),
  [TSC-USER-003](#tsc-user-003),
  [TSC-SOC-003](#tsc-soc-003),
  [TSC-TWEET-003](#tsc-tweet-003),
  [TSC-FEED-003](#tsc-feed-003),
  [TSC-LIKE-003](#tsc-like-003),
  [TSC-NOTIF-003](#tsc-notif-003),
  [TSC-AI-003](#tsc-ai-003).
- **Expected outputs / artifacts:** Threat model/data-flow review; endpoint authorization
  matrix; finalized Redis sliding-window limits and `Retry-After`; CSP/security headers;
  secret/dependency scan configuration; adversarial regression tests; remediation docs.
- **AI-verifiable acceptance criteria:**
  - Every endpoint and WebSocket action has an automated unauthenticated, wrong-user, and
    validation test where applicable.
  - Auth, tweet, social, upload, AI, and global limits return `429`, standard errors, and
    accurate `Retry-After` without cross-user counter leakage.
  - CSP and required headers are present in production-like responses; user content cannot
    execute script or unsafe links in the maintained XSS corpus.
  - Logs and CI artifacts contain no passwords, tokens, cookies, provider prompts/content,
    or committed secrets.
  - Existing configured secret, dependency, lint, type, and security regression checks pass.
- **Verification / evidence:** Attach authorization matrix, adversarial suite output, header
  captures, rate-limit measurements, and scan summaries with sensitive values redacted.
- **Human review gate:** Human approves threat model, residual risks, and rate-limit defaults.

<a id="tsc-hard-002"></a>
### TSC-HARD-002 - Verify reliability and 100-user performance target

- **Status:** To Do
- **Objective / scope:** Measure and tune the production-like stack for approximately 100
  concurrent users without significant degradation, and verify recovery from dependency
  failures. Define and obtain human approval for concrete performance thresholds before
  the first final load run; load results without that prerequisite do not satisfy this
  task. Do not redesign for hyperscale.
- **Dependencies:** [TSC-HARD-001](#tsc-hard-001),
  [TSC-FEED-003](#tsc-feed-003),
  [TSC-NOTIF-003](#tsc-notif-003).
- **Expected outputs / artifacts:** Versioned load scenarios using an existing approved test
  tool; representative seed dataset; latency/error/resource report; SQL/query-count and
  connection-pool evidence; dependency failure/recovery tests; documented budgets.
- **AI-verifiable acceptance criteria:**
  - Human-approved concrete thresholds define "no significant degradation" before the
    final run, including p95 latency, error rate, notification latency, and resource limits.
  - A 100-concurrent-user mixed workload meets those thresholds for the approved duration.
  - Feed/search queries avoid N+1 behavior and use intended indexes under load.
  - PostgreSQL/Redis/worker/storage interruption produces bounded, standard errors and the
    system recovers without data corruption after restoration.
  - All load test inputs/results are reproducible and contain no secrets or real LLM spend.
- **Verification / evidence:** Attach command, environment sizing, machine-readable results,
  threshold comparison, query plans, and recovery-test output.
- **Human review gate:** Human approves thresholds before testing and accepts final results.

<a id="tsc-qa-001"></a>
### TSC-QA-001 - Complete full-system automated acceptance and coverage

- **Status:** To Do
- **Objective / scope:** Close remaining test gaps and run the complete user journey across
  the production-like Compose stack. This task consolidates rather than replaces feature
  tests.
- **Dependencies:** [TSC-HARD-001](#tsc-hard-001),
  [TSC-HARD-002](#tsc-hard-002),
  [TSC-AI-003](#tsc-ai-003).
- **Expected outputs / artifacts:** Full Playwright journey; responsive suites at mobile,
  tablet, desktop; accessibility checks; coverage configuration/reports; flaky-test policy;
  CI artifact retention; release acceptance report.
- **AI-verifiable acceptance criteria:**
  - E2E covers register -> login -> profile edit/avatar -> search -> follow -> tweet with
    image/link -> feed -> like -> reply -> realtime/offline notification -> AI draft ->
    thread summary -> logout.
  - Backend line coverage is at least 80% and frontend line coverage at least 70%, with
    gates enforced in CI rather than report-only.
  - All required viewport suites pass without horizontal overflow or serious automated
    accessibility violations.
  - The complete lint, type, unit, integration, WebSocket, worker, and E2E pipeline passes
    three consecutive times from clean test data.
- **Verification / evidence:** Link coverage and CI artifacts and record three clean full
  pipeline runs with runtime and flaky-retry counts.
- **Human review gate:** Human performs final exploratory acceptance across all breakpoints.

<a id="tsc-ops-001"></a>
### TSC-OPS-001 - Implement production packaging and deployment stack

- **Status:** To Do
- **Objective / scope:** Create the single-VPS production deployment path: versioned
  images, TLS proxy configuration, migrations, health checks, and a repeatable deploy
  command. Release automation, backup/restore, and rollback are owned by `TSC-OPS-002`.
- **Dependencies:** [TSC-FOUND-003](#tsc-found-003),
  [TSC-HARD-001](#tsc-hard-001),
  [TSC-HARD-002](#tsc-hard-002).
- **Expected outputs / artifacts:** Multi-stage production Dockerfiles; Nginx SPA/API/WS
  proxy config with HTTPS/WSS and headers; `docker-compose.prod.yml`; migration pre-start;
  Celery worker/beat; environment/secret contract; `make deploy`; deployment smoke tests.
- **AI-verifiable acceptance criteria:**
  - Production images run as non-root where practical, contain no dev dependencies/secrets,
    and pass image builds/scans.
  - A clean production-like deployment migrates, starts healthy, serves SPA/API/docs per
    policy, upgrades WebSockets, runs workers, and uploads/downloads media.
  - Failed health checks stop the deployment before traffic is served.
  - The full production-like bring-up is reproducible from documented commands only.
- **Verification / evidence:** Record image metadata/scan, production-like smoke test,
  WebSocket proxy test, and migration output.
- **Human review gate:** Human approves deployment target, secret handling, and downtime
  expectations before any real deployment.

<a id="tsc-ops-002"></a>
### TSC-OPS-002 - Implement release automation, backup, and rollback

- **Status:** To Do
- **Objective / scope:** Automate versioned releases and prove operational recovery:
  semver-tag-driven image publishing, gated deploy workflow, PostgreSQL and object-storage
  backup/restore, and a rehearsed rollback procedure.
- **Dependencies:** [TSC-OPS-001](#tsc-ops-001).
- **Expected outputs / artifacts:** Semver tag image-publish workflow with release metadata;
  manual gated deploy workflow; rollback procedure and rehearsal record; PostgreSQL and
  object-storage backup/restore runbook and automation; restore verification checks.
- **AI-verifiable acceptance criteria:**
  - A semver tag publishes matching immutable image tags and release metadata.
  - The deploy workflow requires an explicit manual gate and records the deployed digests.
  - A rehearsed rollback restores the previous version and passes the smoke tests.
  - Backup and restore recreate verified database records and media in an isolated test.
  - No workflow step exposes secrets in logs or artifacts.
- **Verification / evidence:** Record a tag-driven publish run, gated deploy evidence,
  backup/restore checksum comparison, and the rollback rehearsal outcome.
- **Human review gate:** Human approves backup retention and the rollback procedure.

<a id="tsc-doc-001"></a>
### TSC-DOC-001 - Complete living product and developer documentation

- **Status:** To Do
- **Objective / scope:** Ensure a new developer, reviewer, or operator can understand, run,
  test, troubleshoot, and deploy the finished system without relying on task history.
- **Dependencies:** [TSC-QA-001](#tsc-qa-001),
  [TSC-OPS-001](#tsc-ops-001),
  [TSC-OPS-002](#tsc-ops-002).
- **Expected outputs / artifacts:** Root README; local setup and environment reference;
  architecture/data-flow diagrams; ADR index; API/OpenAPI usage; test/coverage guide;
  seed/demo guide; AI provider and cost-control guide; operations/deploy/backup/rollback/
  troubleshooting docs; user-facing feature and limitation summary; changelog.
- **AI-verifiable acceptance criteria:**
  - A clean-checkout documentation walkthrough successfully installs, starts, seeds, tests,
    and stops the application using only documented commands.
  - Every `.env.example` variable is documented and every documented variable exists.
  - Internal links, commands, endpoint references, ports, and file paths are valid.
  - Docs clearly identify v1 non-goals, security assumptions, AI limitations, and recovery
    procedures.
  - OpenAPI generation matches the documented route inventory.
- **Verification / evidence:** Record clean-checkout walkthrough, link/command checks, env
  comparison, and OpenAPI route comparison.
- **Human review gate:** A human unfamiliar with implementation follows the setup/demo guide
  and reports no blocking ambiguity.

<a id="tsc-rel-001"></a>
### TSC-REL-001 - Approve and publish the finished v1 release

- **Status:** To Do
- **Objective / scope:** Perform the final release checklist, resolve all blocking defects,
  publish the first semantic version, deploy it through the approved path, and verify the
  released application. This task does not add new scope.
- **Dependencies:** [TSC-QA-001](#tsc-qa-001),
  [TSC-OPS-001](#tsc-ops-001),
  [TSC-OPS-002](#tsc-ops-002),
  [TSC-DOC-001](#tsc-doc-001).
- **Expected outputs / artifacts:** Completed release checklist; triaged defect list with no
  open blockers; signed/annotated semver tag per policy; release notes; published immutable
  images; deployment record; post-deploy smoke/rollback decision; archived acceptance,
  coverage, security, and performance evidence.
- **AI-verifiable acceptance criteria:**
  - Every preceding task is `Done` and its evidence is linked from its issue/PR.
  - Default-branch CI and the release pipeline pass for the exact tagged commit.
  - Released image digests match deployed image digests.
  - Post-deploy smoke covers health/readiness, auth, profile/search, follow, tweet/media,
    feed, like/reply, notification, and fake/safely configured AI flow.
  - No release-blocking defect, migration error, secret leak, or failed threshold remains.
  - Release notes list features, known limitations, upgrade/rollback steps, and evidence.
- **Verification / evidence:** Link the tag, release, image digests, deployment revision,
  complete CI run, and post-deploy smoke results.
- **Human review gate:** Product/technical owner gives explicit go-live approval.

---

## Progress maintenance checklist

When starting a task:

1. Confirm every listed dependency is `Done`.
2. Create/link the GitHub issue using `[TASK-ID] Title`.
3. Change only that task to `In Progress` and update the progress counts.
4. Restate acceptance criteria in the implementation pull request.

When finishing a task:

1. Run every listed verification step and record exact commands/results.
2. Attach machine-readable reports and human-review artifacts where requested.
3. Update affected living docs and OpenAPI/schema artifacts.
4. Obtain the human review gate.
5. Change the task to `Done`, update progress counts, and unblock dependents.
