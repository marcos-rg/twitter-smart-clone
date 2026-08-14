import { create } from 'zustand'
import type { UserPublic } from '../api/types'

export type SessionStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated'

interface AuthState {
  /** Access token lives here only — in memory, never persisted (spec §7.1, §9.4). */
  accessToken: string | null
  user: UserPublic | null
  status: SessionStatus
  /** Set once, right after a refresh-triggered logout, so the login screen can
   * show a one-time "session expired" message without looping. */
  sessionExpired: boolean
  setLoading: () => void
  /** Successful register/login/refresh+me: store the token and (when known) the user. */
  setSession: (accessToken: string, user?: UserPublic | null) => void
  setAccessToken: (accessToken: string) => void
  /** Explicit user-initiated logout: clear silently, no "expired" messaging. */
  clear: () => void
  /** Refresh failed for a previously-authenticated session: clear + flag it. */
  expireSession: () => void
  acknowledgeExpired: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  status: 'idle',
  sessionExpired: false,
  setLoading: () => set({ status: 'loading' }),
  setSession: (accessToken, user) =>
    set((state) => ({
      accessToken,
      user: user ?? state.user,
      status: 'authenticated',
      sessionExpired: false,
    })),
  setAccessToken: (accessToken) => set({ accessToken }),
  clear: () =>
    set({ accessToken: null, user: null, status: 'unauthenticated', sessionExpired: false }),
  expireSession: () =>
    set((state) => ({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
      // Only surface the "expired" message if there actually was a session to lose.
      sessionExpired: state.status === 'authenticated',
    })),
  acknowledgeExpired: () => set({ sessionExpired: false }),
}))
