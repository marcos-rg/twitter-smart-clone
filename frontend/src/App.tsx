import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { ToastProvider } from './components/ui'
import { useSessionBootstrap } from './features/auth/hooks'
import { Home } from './routes/Home'
import { Lab } from './routes/Lab'
import { Login } from './routes/Login'
import { Register } from './routes/Register'
import { ProtectedRoute, PublicOnlyRoute } from './routes/guards/RouteGuards'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

/** Restores the session (refresh cookie + `/auth/me`) once, before the rest
 * of the tree renders — keeps the bootstrap effect out of `App` itself so
 * tests can render `App` without worrying about ordering. */
function SessionBootstrap({ children }: { children: import('react').ReactNode }) {
  useSessionBootstrap()
  return <>{children}</>
}

/**
 * Root component: router + global providers + responsive application shell.
 * `/lab` is the in-app component interaction lab (TSC-UX-001); `/login` and
 * `/register` are public-only (TSC-AUTH-002); `/` requires an authenticated
 * session. Further feature routes are added by later tasks.
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <SessionBootstrap>
            <AppShell>
              <Routes>
                <Route
                  path="/"
                  element={
                    <ProtectedRoute>
                      <Home />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/login"
                  element={
                    <PublicOnlyRoute>
                      <Login />
                    </PublicOnlyRoute>
                  }
                />
                <Route
                  path="/register"
                  element={
                    <PublicOnlyRoute>
                      <Register />
                    </PublicOnlyRoute>
                  }
                />
                <Route path="/lab" element={<Lab />} />
              </Routes>
            </AppShell>
          </SessionBootstrap>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}

export default App
