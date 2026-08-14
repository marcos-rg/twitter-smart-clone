import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import * as authApi from '../../api/auth'
import { ApiError } from '../../api/client'
import { useAuthStore } from '../../stores/auth-store'
import type { LoginPayload, RegisterPayload } from '../../api/types'

/** Human-readable message for any thrown error, preferring the server's
 * user-safe `message` (spec §6.2) and falling back for network failures. */
export function describeAuthError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Check your connection and try again.'
}

export function useRegister() {
  return useMutation({
    mutationFn: (payload: RegisterPayload) => authApi.register(payload),
  })
}

/** Login stores the returned access token + user directly — no extra
 * `/auth/me` round trip needed since `/auth/login` embeds the user. */
export function useLogin() {
  const setSession = useAuthStore((state) => state.setSession)
  return useMutation({
    mutationFn: (payload: LoginPayload) => authApi.login(payload),
    onSuccess: (data) => {
      setSession(data.access_token, data.user ?? null)
    },
  })
}

export function useLogout() {
  const clear = useAuthStore((state) => state.clear)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => authApi.logout(),
    onSettled: () => {
      // Clear client state even if the network call failed — the user asked
      // to log out and the UI must reflect that immediately.
      clear()
      queryClient.clear()
    },
  })
}

/** Runs once on app mount: attempts to rotate the refresh cookie into a new
 * access token and, on success, fetches the current user — restoring the
 * session across a reload (spec §7.1 acceptance criterion). Leaves the store
 * in `unauthenticated` (no toast) when there is no valid session to restore. */
export function useSessionBootstrap() {
  const setLoading = useAuthStore((state) => state.setLoading)
  const setSession = useAuthStore((state) => state.setSession)
  const clear = useAuthStore((state) => state.clear)
  const ranRef = useRef(false)

  useEffect(() => {
    if (ranRef.current) return
    ranRef.current = true

    let cancelled = false
    setLoading()

    async function bootstrap() {
      try {
        const tokenData = await authApi.refresh()
        if (cancelled) return
        useAuthStore.getState().setAccessToken(tokenData.access_token)
        const user = await authApi.getCurrentUser()
        if (cancelled) return
        setSession(tokenData.access_token, user)
      } catch {
        if (!cancelled) clear()
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
