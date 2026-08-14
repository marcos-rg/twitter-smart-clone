import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Skeleton } from '../../components/ui'
import { useAuthStore } from '../../stores/auth-store'

export interface RouteGuardProps {
  children: ReactNode
}

/** Wraps routes that require an authenticated session. While the session is
 * still being restored (initial refresh + `/auth/me`) it shows a loading
 * skeleton instead of redirecting, so a valid session never flashes a login
 * screen. Once restoration finishes, unauthenticated users are redirected to
 * `/login` with the attempted location so they land back where they started
 * (spec §7.1, §9.3). */
export function ProtectedRoute({ children }: RouteGuardProps) {
  const status = useAuthStore((state) => state.status)
  const location = useLocation()

  if (status === 'idle' || status === 'loading') {
    return (
      <div className="p-4">
        <Skeleton className="h-24 w-full" label="Restoring your session" />
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <>{children}</>
}

/** Wraps routes that should never be visible to an authenticated user
 * (login, register). Redirects straight to the home feed once a session is
 * confirmed. */
export function PublicOnlyRoute({ children }: RouteGuardProps) {
  const status = useAuthStore((state) => state.status)

  if (status === 'idle' || status === 'loading') {
    return (
      <div className="p-4">
        <Skeleton className="h-24 w-full" label="Restoring your session" />
      </div>
    )
  }

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
