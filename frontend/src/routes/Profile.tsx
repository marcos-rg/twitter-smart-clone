import { useNavigate, useParams } from 'react-router-dom'
import { Button, EmptyState, ErrorState, Skeleton } from '../components/ui'
import { TweetCard, TweetCardSkeleton } from '../components/tweet/TweetCard'
import { ProfileHeader } from '../features/users/ProfileHeader'
import { describeUsersError, useProfile, useUserTweets } from '../features/users/hooks'
import { TweetComposer } from '../features/tweets/TweetComposer'
import { useAuthStore } from '../stores/auth-store'

/**
 * Own/other profile screen: header (avatar, name, bio, join date, edit
 * affordance) plus the user's tweet timeline, cursor-paginated. Works
 * identically for the signed-in user's own profile and anyone else's — the
 * only difference is whether "Edit profile" renders, decided by comparing
 * the route's `:username` to the signed-in user (case-insensitively, since
 * usernames are unique case-insensitively on the backend).
 */
export function Profile() {
  const { username } = useParams<{ username: string }>()
  const navigate = useNavigate()
  const currentUsername = useAuthStore((state) => state.user?.username)
  const isOwnProfile = Boolean(
    username && currentUsername && username.toLowerCase() === currentUsername.toLowerCase(),
  )

  const profile = useProfile(username)
  const tweets = useUserTweets(username)

  if (profile.isLoading) {
    return (
      <div className="p-4">
        <Skeleton className="h-48 w-full" label="Loading profile" />
      </div>
    )
  }

  if (profile.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Couldn't load this profile"
          description={describeUsersError(profile.error)}
          onRetry={() => void profile.refetch()}
        />
      </div>
    )
  }

  if (!profile.data) return null

  const items = tweets.data?.pages.flatMap((page) => page.data) ?? []

  return (
    <div>
      <ProfileHeader
        name={profile.data.name}
        username={profile.data.username}
        bio={profile.data.bio}
        avatarKey={profile.data.avatar_key}
        createdAt={profile.data.created_at}
        isOwnProfile={isOwnProfile}
        onEdit={() => navigate(`/profile/${profile.data.username}/edit`)}
        followersCount={profile.data.followers_count}
        followingCount={profile.data.following_count}
        isFollowing={profile.data.is_following}
      />

      {isOwnProfile ? <TweetComposer profileUsername={profile.data.username} /> : null}

      <div>
        {tweets.isLoading ? (
          <>
            <TweetCardSkeleton />
            <TweetCardSkeleton />
            <TweetCardSkeleton />
          </>
        ) : tweets.isError ? (
          <div className="p-4">
            <ErrorState
              title="Couldn't load tweets"
              description={describeUsersError(tweets.error)}
              onRetry={() => void tweets.refetch()}
            />
          </div>
        ) : items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No tweets yet"
              description={
                isOwnProfile
                  ? 'When you post, your tweets will show up here.'
                  : `@${profile.data.username} hasn't posted anything yet.`
              }
            />
          </div>
        ) : (
          <>
            {items.map((tweet) => (
              <TweetCard key={tweet.id} tweet={tweet} />
            ))}
            {tweets.hasNextPage ? (
              <div className="flex justify-center p-4">
                <Button
                  variant="outline"
                  loading={tweets.isFetchingNextPage}
                  onClick={() => void tweets.fetchNextPage()}
                >
                  Load more
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
