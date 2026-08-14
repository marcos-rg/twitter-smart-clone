import { useRef } from 'react'
import { Button, useToast } from '../../components/ui'
import { describeUsersError } from '../users/hooks'
import { useFollowMutation } from './hooks'

export interface FollowButtonProps {
  username: string
  isFollowing: boolean
  /** Renders nothing for the signed-in user's own profile — self-follow is
   * impossible on the backend, so there is no control to show. */
  isOwnProfile: boolean
}

/**
 * Follow/unfollow control for a profile (TSC-SOC-002).
 *
 * Three states:
 * - own profile: renders nothing.
 * - not following: solid "Follow" button; clicking it follows.
 * - following: outline "Following" button (`aria-pressed="true"`); clicking
 *   it unfollows.
 *
 * A synchronous ref guard (`pendingRef`), not just the mutation's `isPending`
 * flag, blocks a second submit from a rapid double click: `isPending` only
 * becomes true after React commits the state update `mutate()` schedules, so
 * two clicks dispatched in the same tick would both read `isPending: false`
 * and both fire a request without this guard (acceptance criterion:
 * "repeated rapid clicks cannot issue contradictory concurrent mutations").
 */
export function FollowButton({ username, isFollowing, isOwnProfile }: FollowButtonProps) {
  const mutation = useFollowMutation(username)
  const { toast } = useToast()
  const pendingRef = useRef(false)

  if (isOwnProfile) return null

  function handleClick() {
    if (pendingRef.current) return
    pendingRef.current = true
    const nextFollowing = !isFollowing
    mutation.mutate(nextFollowing, {
      onError: (error) => {
        toast(
          nextFollowing
            ? `Couldn't follow @${username}. ${describeUsersError(error)}`
            : `Couldn't unfollow @${username}. ${describeUsersError(error)}`,
          'error',
        )
      },
      onSettled: () => {
        pendingRef.current = false
      },
    })
  }

  return (
    <Button
      type="button"
      variant={isFollowing ? 'outline' : 'primary'}
      size="sm"
      loading={mutation.isPending}
      onClick={handleClick}
      aria-pressed={isFollowing}
    >
      {isFollowing ? 'Following' : 'Follow'}
    </Button>
  )
}
