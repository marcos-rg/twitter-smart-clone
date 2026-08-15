import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { ToastProvider } from './components/ui'
import { useSessionBootstrap } from './features/auth/hooks'
import { useNotificationsSocket } from './features/notifications/hooks'
import { Followers } from './routes/Followers'
import { Following } from './routes/Following'
import { Home } from './routes/Home'
import { Lab } from './routes/Lab'
import { Login } from './routes/Login'
import { Notifications } from './routes/Notifications'
import { Profile } from './routes/Profile'
import { ProfileEdit } from './routes/ProfileEdit'
import { Register } from './routes/Register'
import { Search } from './routes/Search'
import { TweetDetail } from './routes/TweetDetail'
import { ProtectedRoute, PublicOnlyRoute } from './routes/guards/RouteGuards'

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

/** Restores the session (refresh cookie + `/auth/me`) once, before the rest
 * of the tree renders — keeps the bootstrap effect out of `App` itself so
 * tests can render `App` without worrying about ordering. */
function SessionBootstrap({ children }: { children: import('react').ReactNode }) {
  useSessionBootstrap()
  return <>{children}</>
}

/** Owns the realtime notifications WebSocket connection for the lifetime of
 * the app (TSC-NOTIF-002) — connects once a session is restored, reconnects
 * with backoff on drop, and disconnects + clears notification state on
 * logout. Kept as its own no-render component (like `SessionBootstrap`) so
 * tests can render `App` without needing to reason about the socket. */
function NotificationsSocketBridge({ children }: { children: import('react').ReactNode }) {
  useNotificationsSocket()
  return <>{children}</>
}

/**
 * Root component: router + global providers + responsive application shell.
 * `/lab` is the in-app component interaction lab (TSC-UX-001); `/login` and
 * `/register` are public-only (TSC-AUTH-002); `/`, `/search`,
 * `/notifications`, `/profile/:username`, `/profile/:username/edit`,
 * `/profile/:username/followers`, `/profile/:username/following`, and
 * `/tweet/:tweetId` require an authenticated session
 * (`/profile/:username/edit` further redirects to the read-only profile
 * unless `:username` is the signed-in user — TSC-USER-002; the
 * followers/following routes are the follow/social-list slice —
 * TSC-SOC-002; `/tweet/:tweetId` is the tweet-detail/reply screen —
 * TSC-TWEET-002; `/notifications` is the realtime notifications panel —
 * TSC-NOTIF-002). Further feature routes are added by later tasks.
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <SessionBootstrap>
            <NotificationsSocketBridge>
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
                  <Route
                    path="/search"
                    element={
                      <ProtectedRoute>
                        <Search />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/notifications"
                    element={
                      <ProtectedRoute>
                        <Notifications />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/profile/:username/edit"
                    element={
                      <ProtectedRoute>
                        <ProfileEdit />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/profile/:username/followers"
                    element={
                      <ProtectedRoute>
                        <Followers />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/profile/:username/following"
                    element={
                      <ProtectedRoute>
                        <Following />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/profile/:username"
                    element={
                      <ProtectedRoute>
                        <Profile />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/tweet/:tweetId"
                    element={
                      <ProtectedRoute>
                        <TweetDetail />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="/lab" element={<Lab />} />
                </Routes>
              </AppShell>
            </NotificationsSocketBridge>
          </SessionBootstrap>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}

export default App
