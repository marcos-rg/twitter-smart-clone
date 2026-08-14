import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { toHaveNoViolations } from 'jest-axe'
import { afterAll, afterEach, beforeAll, expect } from 'vitest'
import { server } from './mocks/server'
import { useAuthStore } from '../src/stores/auth-store'

// vitest runs with globals: false, so RTL's automatic cleanup is not wired up.
afterEach(() => cleanup())

expect.extend(toHaveNoViolations)

// MSW: intercept network calls (the auth API client's fetch) at the node
// level for every test. `resetHandlers` restores the default handlers after
// any test-specific `server.use(...)` overrides.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// The auth store is a module-level singleton — reset it between tests so
// login/logout/session state never leaks across test files.
afterEach(() => {
  useAuthStore.setState({
    accessToken: null,
    user: null,
    status: 'idle',
    sessionExpired: false,
  })
})

// jsdom doesn't implement the Blob URL registry, so `useImageUploader`
// (TSC-MEDIA-002) can't call `URL.createObjectURL`/`revokeObjectURL`
// directly in tests. A minimal counter-based fake is enough: tests only need
// stable, distinct strings and a way to assert `revokeObjectURL` was called
// for cleanup, not real blob resolution.
let objectUrlCounter = 0
URL.createObjectURL = (() => `blob:mock-${objectUrlCounter++}`) as typeof URL.createObjectURL
URL.revokeObjectURL = (() => {}) as typeof URL.revokeObjectURL

// jsdom doesn't implement `window.scrollTo` (no real layout/rendering), so
// calling it logs a "Not implemented" error and leaves `scrollY` at 0. The
// home feed's scroll-restoration hook (TSC-FEED-002) calls it to restore
// position on back navigation; tests stub both `scrollTo` and a writable
// `scrollY` so that behavior is actually observable under jsdom.
Object.defineProperty(window, 'scrollY', { value: 0, writable: true, configurable: true })
window.scrollTo = ((x?: number | ScrollToOptions, y?: number) => {
  const target = typeof x === 'object' ? (x.top ?? window.scrollY) : (y ?? 0)
  Object.defineProperty(window, 'scrollY', { value: target, writable: true, configurable: true })
}) as typeof window.scrollTo

// jsdom has no `IntersectionObserver` implementation. This harmless no-op
// stub is enough for any test that renders the feed's sentinel without
// caring about pagination itself (it simply never fires); tests that need
// to *drive* an intersection (`tests/features/feed/Feed.test.tsx`) install
// their own controllable mock via `vi.stubGlobal`, which wins for the
// duration of that test file and is restored to this default afterward.
class NoopIntersectionObserver implements IntersectionObserver {
  readonly root = null
  readonly rootMargin = ''
  readonly thresholds: number[] = []
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}
window.IntersectionObserver = NoopIntersectionObserver as unknown as typeof IntersectionObserver

// `App` renders a real `BrowserRouter`, which reads `window.location` at
// mount. jsdom's `window` (and therefore its history) is shared across every
// `it()` in a test file, so without this a test that navigates (e.g. to
// `/profile/ada`) would leave the *next* test's `render(<App />)` starting
// from that URL instead of `/`.
afterEach(() => {
  window.history.pushState({}, '', '/')
  window.scrollTo(0, 0)
  window.sessionStorage.clear()
})
