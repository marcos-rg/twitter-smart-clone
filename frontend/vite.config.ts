/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      // Ratcheting coverage gate (TSC-FOUND-003): raised as features land so
      // the final 70% line-coverage gate in TSC-QA-001 is not a last-minute
      // cliff. CI fails `npm run test -- --coverage` if coverage drops below
      // these thresholds; bump them upward whenever a feature task lands
      // with well-tested code.
      thresholds: {
        lines: 50,
        statements: 50,
        functions: 50,
        branches: 50,
      },
    },
  },
})
