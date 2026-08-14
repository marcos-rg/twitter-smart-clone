import { Button, EmptyState, ErrorState } from '../../components/ui'
import { TweetCard, TweetCardSkeleton } from '../../components/tweet/TweetCard'
import { describeTweetsError, useReplies } from './hooks'

export interface ReplyListProps {
  tweetId: string
}

/** Flat replies to a tweet, oldest first, cursor-paginated — mirrors
 * `Profile.tsx`'s timeline loading/empty/error/pagination pattern. Listing
 * replies of a reply is always an empty page (never an error): no reply can
 * ever have replies (flat-reply model, see `docs/tweet-backend.md`). */
export function ReplyList({ tweetId }: ReplyListProps) {
  const replies = useReplies(tweetId)
  const items = replies.data?.pages.flatMap((page) => page.data) ?? []

  if (replies.isLoading) {
    return (
      <>
        <TweetCardSkeleton />
        <TweetCardSkeleton />
      </>
    )
  }

  if (replies.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Couldn't load replies"
          description={describeTweetsError(replies.error)}
          onRetry={() => void replies.refetch()}
        />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="p-4">
        <EmptyState title="No replies yet" description="Be the first to reply." />
      </div>
    )
  }

  return (
    <>
      {items.map((tweet) => (
        <TweetCard key={tweet.id} tweet={tweet} />
      ))}
      {replies.hasNextPage ? (
        <div className="flex justify-center p-4">
          <Button
            variant="outline"
            loading={replies.isFetchingNextPage}
            onClick={() => void replies.fetchNextPage()}
          >
            Load more
          </Button>
        </div>
      ) : null}
    </>
  )
}
