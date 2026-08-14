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

// `App` renders a real `BrowserRouter`, which reads `window.location` at
// mount. jsdom's `window` (and therefore its history) is shared across every
// `it()` in a test file, so without this a test that navigates (e.g. to
// `/profile/ada`) would leave the *next* test's `render(<App />)` starting
// from that URL instead of `/`.
afterEach(() => {
  window.history.pushState({}, '', '/')
})
