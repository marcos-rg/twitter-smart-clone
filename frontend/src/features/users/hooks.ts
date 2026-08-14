import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as usersApi from '../../api/users'
import { ApiError } from '../../api/client'
import { useAuthStore } from '../../stores/auth-store'
import type { SearchMode, UserProfileUpdateRequest } from '../../api/types'

/** Human-readable message for any thrown error (mirrors
 * `features/auth/hooks.describeAuthError`). */
export function describeUsersError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Check your connection and try again.'
}

export function profileQueryKey(username: string | undefined) {
  return ['profile', username?.toLowerCase()] as const
}

/** Public profile lookup by username (case-insensitive on the backend).
 * Disabled until a username is known (e.g. route params still resolving). */
export function useProfile(username: string | undefined) {
  return useQuery({
    queryKey: profileQueryKey(username),
    queryFn: () => usersApi.getProfile(username as string),
    enabled: Boolean(username),
  })
}

/** Edits the signed-in user's own profile. On success, refreshes the
 * in-memory auth store (so the header/nav reflect the new name/username
 * immediately) and the cached profile for both the old and new username. */
export function useUpdateProfile() {
  const queryClient = useQueryClient()
  const setSession = useAuthStore((state) => state.setSession)

  return useMutation({
    mutationFn: (payload: UserProfileUpdateRequest) => usersApi.updateMyProfile(payload),
    onSuccess: (user) => {
      const accessToken = useAuthStore.getState().accessToken
      if (accessToken) setSession(accessToken, user)
      queryClient.setQueryData(profileQueryKey(user.username), user)
      void queryClient.invalidateQueries({ queryKey: ['profile'] })
    },
  })
}

const TIMELINE_PAGE_SIZE = 20

/** A profile's own tweets, cursor-paginated (spec §7.2). */
export function useUserTweets(username: string | undefined) {
  return useInfiniteQuery({
    queryKey: ['user-tweets', username?.toLowerCase()],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      usersApi.getUserTweets(username as string, { cursor: pageParam, limit: TIMELINE_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    enabled: Boolean(username),
  })
}

const SEARCH_PAGE_SIZE = 20

/** User search, cursor-paginated per mode. Deliberately does NOT set
 * `placeholderData` (no `keepPreviousData`): a new `query`/`mode` gets a
 * fresh query key with no data yet, so the UI shows a loading state instead
 * of the previous query's results while the new request is in flight —
 * required so rapid typing never flashes stale matches (TSC-USER-002
 * acceptance criterion). Callers should debounce `query` themselves (see
 * `useDebouncedValue`) so this isn't refetched on every keystroke. */
export function useUserSearch(query: string, mode: SearchMode) {
  const trimmed = query.trim()
  return useInfiniteQuery({
    queryKey: ['user-search', mode, trimmed],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      usersApi.searchUsers({ q: trimmed, mode, cursor: pageParam, limit: SEARCH_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    enabled: trimmed.length > 0,
  })
}
