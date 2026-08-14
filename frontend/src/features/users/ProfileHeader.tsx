import { Avatar, Button } from '../../components/ui'

export interface ProfileHeaderProps {
  name: string
  username: string
  bio: string | null
  /** Object key for an uploaded avatar. Avatar binary upload/serving lands in
   * TSC-MEDIA-001/002 — until there's a URL-resolution helper for it, the
   * header always falls back to initials rather than guessing a URL shape. */
  avatarKey: string | null
  createdAt: string
  isOwnProfile: boolean
  /** Navigates to the edit screen. Only rendered/called for `isOwnProfile`. */
  onEdit?: () => void
}

/**
 * Profile header: avatar, display name, @handle, join date, and bio. Never
 * renders an email address — the backend's public-profile response has no
 * `email` field for anyone, including the owner viewing their own profile
 * (spec: "never expose email on a public profile").
 */
export function ProfileHeader({
  name,
  username,
  bio,
  avatarKey,
  createdAt,
  isOwnProfile,
  onEdit,
}: ProfileHeaderProps) {
  void avatarKey
  return (
    <header className="flex flex-col gap-4 border-b border-border px-4 py-6">
      <div className="flex items-start justify-between gap-4">
        <Avatar name={name} size="lg" />
        {isOwnProfile ? (
          <Button variant="outline" size="sm" onClick={onEdit}>
            Edit profile
          </Button>
        ) : null}
      </div>
      <div className="min-w-0">
        <h1 className="truncate text-xl font-bold text-foreground">{name}</h1>
        <p className="text-sm text-muted">@{username}</p>
      </div>
      {bio ? <p className="whitespace-pre-wrap break-words text-foreground">{bio}</p> : null}
      <p className="text-sm text-muted">Joined {formatJoinedDate(createdAt)}</p>
    </header>
  )
}

function formatJoinedDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}
