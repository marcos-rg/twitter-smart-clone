import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { toHaveNoViolations } from 'jest-axe'
import { afterEach, expect } from 'vitest'

// vitest runs with globals: false, so RTL's automatic cleanup is not wired up.
afterEach(() => cleanup())

expect.extend(toHaveNoViolations)
