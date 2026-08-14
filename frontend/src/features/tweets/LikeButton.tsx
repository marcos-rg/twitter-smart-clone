import { useRef, useState } from 'react'
import { useToast } from '../../components/ui'
import { describeTweetsError, useLikeMutation } from './hooks'
import type { TweetView } from '../../api/types'

export interface LikeButtonProps {
  tweet: TweetView
}

/**
 * Like/unlike control for a tweet card or detail (TSC-LIKE-002).
 *
 * Two states, mirroring `FollowButton`:
 * - not liked: outline heart; clicking it likes.
 * - liked: filled heart in the danger color (`aria-pressed="true"`); clicking
 *   it unlikes.
 *
 * A synchronous ref guard (`pendingRef`), not just the mutation's `isPending`
 * flag, blocks a second submit from a rapid double click — see
 * `useLikeMutation`'s doc comment for why `isPending` alone isn't enough
 * (acceptance criterion: "rapid clicks cannot produce negative counts or
 * contradictory requests"). The button is also `disabled` while pending, so
 * it can't be activated by keyboard either.
 *
 * A brief "pop" animation plays on the heart glyph when a like newly lands
 * (`animate-like-pop`, defined in `index.css`) — purely decorative
 * (`aria-hidden`), and both the app-wide `prefers-reduced-motion` rule and
 * this element's own `motion-reduce:animate-none` disable it for users who
 * asked for reduced motion.
 */
export function LikeButton({ tweet }: LikeButtonProps) {
  const mutation = useLikeMutation(tweet.id)
  const { toast } = useToast()
  const pendingRef = useRef(false)
  const [pop, setPop] = useState(false)

  function handleClick(event: React.MouseEvent<HTMLButtonElement>) {
    event.stopPropagation()
    if (pendingRef.current) return
    pendingRef.current = true
    const nextLiked = !tweet.liked_by_viewer
    if (nextLiked) setPop(true)
    mutation.mutate(nextLiked, {
      onError: (error) => {
        toast(
          nextLiked
            ? `Couldn't like this tweet. ${describeTweetsError(error)}`
            : `Couldn't unlike this tweet. ${describeTweetsError(error)}`,
          'error',
        )
      },
      onSettled: () => {
        pendingRef.current = false
      },
    })
  }

  return (
    <button
      type="button"
      disabled={mutation.isPending}
      aria-pressed={tweet.liked_by_viewer}
      aria-label={`${tweet.liked_by_viewer ? 'Liked' : 'Like'}, ${tweet.like_count} likes`}
      onClick={handleClick}
      className={`flex cursor-pointer items-center gap-1 rounded-full px-2 py-1 transition-colors duration-150 hover:bg-danger/10 hover:text-danger motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-70 ${
        tweet.liked_by_viewer ? 'text-danger' : ''
      }`}
    >
      <span
        aria-hidden="true"
        onAnimationEnd={() => setPop(false)}
        className={
          pop ? 'inline-block animate-like-pop motion-reduce:animate-none' : 'inline-block'
        }
      >
        {tweet.liked_by_viewer ? '❤' : '♡'}
      </span>
      <span aria-hidden="true">{tweet.like_count}</span>
    </button>
  )
}
