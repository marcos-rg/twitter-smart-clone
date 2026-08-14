import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { ErrorState } from '../components/ui'
import { TweetCard, TweetCardSkeleton } from '../components/tweet/TweetCard'
import { TweetComposer } from '../features/tweets/TweetComposer'
import { ReplyList } from '../features/tweets/ReplyList'
import { describeTweetsError, useTweet } from '../features/tweets/hooks'

/**
 * Tweet detail screen (`/tweet/:tweetId`): the tweet itself, a reply
 * composer (root tweets only), and its flat replies.
 *
 * Nested-reply safety (human-review focus): a reply can never be replied to
 * — the backend rejects it with 422. So when the fetched tweet is itself a
 * reply (`parent_tweet_id !== null`), no reply composer is rendered at all;
 * only root tweets (`parent_tweet_id === null`) get one.
 *
 * A missing/malformed/unknown id fails safely into an `ErrorState` rather
 * than an unhandled exception or a blank screen.
 */
export function TweetDetail() {
  const { tweetId } = useParams<{ tweetId: string }>()
  const tweet = useTweet(tweetId)

  if (!tweetId) {
    return (
      <div className="p-4">
        <ErrorState title="Tweet not found" description="No tweet id was provided." />
      </div>
    )
  }

  if (tweet.isLoading) {
    return (
      <div>
        <TweetCardSkeleton />
      </div>
    )
  }

  if (tweet.isError) {
    const notFound = tweet.error instanceof ApiError && tweet.error.status === 404
    return (
      <div className="p-4">
        <ErrorState
          title={notFound ? 'Tweet not found' : "Couldn't load this tweet"}
          description={
            notFound
              ? 'This tweet may have been removed, or never existed.'
              : describeTweetsError(tweet.error)
          }
          onRetry={notFound ? undefined : () => void tweet.refetch()}
        />
      </div>
    )
  }

  if (!tweet.data) return null

  const isRoot = tweet.data.parent_tweet_id === null

  return (
    <div>
      <TweetCard tweet={tweet.data} />
      {isRoot ? <TweetComposer parentTweetId={tweet.data.id} /> : null}
      <ReplyList tweetId={tweet.data.id} />
    </div>
  )
}
