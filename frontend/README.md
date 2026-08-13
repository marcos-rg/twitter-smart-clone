# Frontend

React 18 + Vite + TypeScript single-page application for the Twitter Smart
Clone. See [specification/specification.md](../specification/specification.md)
for the full architecture and [docs/](../docs) for living documentation.

## Prerequisites

- Node.js 24+ and npm 11+.

## Commands

| Command                | Description                                    |
| ---------------------- | ---------------------------------------------- |
| `npm ci`               | Install dependencies from `package-lock.json`. |
| `npm run dev`          | Start the Vite dev server with HMR.            |
| `npm run build`        | Type-check and build the production bundle.    |
| `npm run preview`      | Serve the production build locally.            |
| `npm run typecheck`    | Run `tsc` in strict mode with no emit.         |
| `npm run lint`         | Run ESLint.                                    |
| `npm run format`       | Format the codebase with Prettier.             |
| `npm run format:check` | Check formatting without writing changes.      |
| `npm run test`         | Run Vitest unit/component tests once.          |
| `npm run test:watch`   | Run Vitest in watch mode.                      |
| `npm run e2e`          | Run Playwright end-to-end tests.               |

## Project structure

```
src/
├── api/          # API client, TanStack Query hooks
├── components/   # Shared UI components
├── features/     # feed, tweet, profile, notifications, search, ai
├── stores/       # Zustand stores
├── routes/       # React Router routes
├── lib/          # ws client, utils
└── main.tsx
tests/            # Vitest + React Testing Library
e2e/              # Playwright
```
