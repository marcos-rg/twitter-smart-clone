import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as followsApi from '../../api/follows'
import { profileQueryKey } from '../users/hooks'
import type { UserPublicProfile } from '../../api/types'

const LIST_PAGE_SIZE = 20

export function followersQueryKey(username: string | undefined) {
  return ['followers', username?.toLowerCase()] as const
}

export function followingQueryKey(username: string | undefined) {
  return ['following', username?.toLowerCase()] as const
}

/** A user's followers, cursor-paginated (TSC-SOC-001). */
export function useFollowers(username: string | undefined) {
  return useInfiniteQuery({
    queryKey: followersQueryKey(username),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      followsApi.getFollowers(username as string, { cursor: pageParam, limit: LIST_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    enabled: Boolean(username),
  })
}

/** Who a user follows, cursor-paginated (TSC-SOC-001). */
export function useFollowing(username: string | undefined) {
  return useInfiniteQuery({
    queryKey: followingQueryKey(username),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      followsApi.getFollowing(username as string, { cursor: pageParam, limit: LIST_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    enabled: Boolean(username),
  })
}

/**
 * Follow/unfollow a profile with an optimistic update and full rollback on
 * failure (TSC-SOC-002 acceptance criteria).
 *
 * `mutate(nextFollowing)` flips the cached profile's `is_following` and
 * `followers_count` immediately, before the network call resolves. If the
 * request fails, the exact pre-mutation snapshot is restored — not just
 * `is_following`, so a failed follow/unfollow never leaves the count off by
 * one. On success the server's authoritative `following`/`followers_count`
 * replace the optimistic guess (idempotent follow/unfollow can mean the
 * server's count doesn't move even though the optimistic update assumed it
 * would, e.g. a repeat call).
 *
 * Callers are responsible for not calling `mutate` again while
 * `isPending` is true — `FollowButton` enforces this with both a disabled
 * button and a synchronous ref guard, since React state updates that back
 * `isPending` are not visible within the same synchronous click handler that
 * fired the first click (acceptance criterion: "repeated rapid clicks cannot
 * issue contradictory concurrent mutations").
 */
export function useFollowMutation(username: string | undefined) {
  const queryClient = useQueryClient()
  const key = profileQueryKey(username)

  return useMutation({
    mutationFn: (nextFollowing: boolean) =>
      nextFollowing
        ? followsApi.followUser(username as string)
        : followsApi.unfollowUser(username as string),
    onMutate: async (nextFollowing: boolean) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<UserPublicProfile>(key)
      if (previous) {
        queryClient.setQueryData<UserPublicProfile>(key, {
          ...previous,
          is_following: nextFollowing,
          followers_count: Math.max(
            0,
            previous.followers_count +
              (nextFollowing ? 1 : -1) * (previous.is_following === nextFollowing ? 0 : 1),
          ),
        })
      }
      return { previous }
    },
    onError: (_error, _nextFollowing, context) => {
      if (context?.previous) {
        queryClient.setQueryData(key, context.previous)
      }
    },
    onSuccess: (result) => {
      queryClient.setQueryData<UserPublicProfile>(key, (current) =>
        current
          ? { ...current, is_following: result.following, followers_count: result.followers_count }
          : current,
      )
    },
  })
}
