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
