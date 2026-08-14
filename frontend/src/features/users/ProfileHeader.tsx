import { Link } from 'react-router-dom'
import { Avatar, Button } from '../../components/ui'
import { resolveMediaUrl } from '../../api/media'
import { FollowButton } from '../follows/FollowButton'

export interface ProfileHeaderProps {
  name: string
  username: string
  bio: string | null
  /** Object key for an uploaded avatar, resolved to a URL via
   * `resolveMediaUrl` (TSC-MEDIA-002). `Avatar` falls back to initials
   * itself if this is `null` or the image fails to load. */
  avatarKey: string | null
  createdAt: string
  isOwnProfile: boolean
  /** Navigates to the edit screen. Only rendered/called for `isOwnProfile`. */
  onEdit?: () => void
  followersCount: number
  followingCount: number
  /** Whether the signed-in user follows this profile. Ignored (and the
   * follow control hidden) when `isOwnProfile` is true. */
  isFollowing: boolean
}

/**
 * Profile header: avatar, display name, @handle, join date, bio, and
 * follower/following counts (linking to the paginated lists) plus a
 * follow/unfollow control (TSC-SOC-002). Never renders an email address —
 * the backend's public-profile response has no `email` field for anyone,
 * including the owner viewing their own profile (spec: "never expose email
 * on a public profile").
 */
export function ProfileHeader({
  name,
  username,
  bio,
  avatarKey,
  createdAt,
  isOwnProfile,
  onEdit,
  followersCount,
  followingCount,
  isFollowing,
}: ProfileHeaderProps) {
  return (
    <header className="flex flex-col gap-4 border-b border-border px-4 py-6">
      <div className="flex items-start justify-between gap-4">
        <Avatar name={name} src={resolveMediaUrl(avatarKey)} size="lg" />
        {isOwnProfile ? (
          <Button variant="outline" size="sm" onClick={onEdit}>
            Edit profile
          </Button>
        ) : (
          <FollowButton username={username} isFollowing={isFollowing} isOwnProfile={isOwnProfile} />
        )}
      </div>
      <div className="min-w-0">
        <h1 className="truncate text-xl font-bold text-foreground">{name}</h1>
        <p className="text-sm text-muted">@{username}</p>
      </div>
      {bio ? <p className="whitespace-pre-wrap break-words text-foreground">{bio}</p> : null}
      <div className="flex gap-4 text-sm">
        <Link to={`/profile/${username}/following`} className="hover:underline">
          <span className="font-semibold text-foreground">{followingCount}</span>{' '}
          <span className="text-muted">Following</span>
        </Link>
        <Link to={`/profile/${username}/followers`} className="hover:underline">
          <span className="font-semibold text-foreground">{followersCount}</span>{' '}
          <span className="text-muted">{followersCount === 1 ? 'Follower' : 'Followers'}</span>
        </Link>
      </div>
      <p className="text-sm text-muted">Joined {formatJoinedDate(createdAt)}</p>
    </header>
  )
}

function formatJoinedDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}
