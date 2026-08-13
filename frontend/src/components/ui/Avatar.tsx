import { useState } from 'react'

type AvatarSize = 'sm' | 'md' | 'lg'

export interface AvatarProps {
  /** Display name — used for the alt text and the initials fallback. */
  name: string
  src?: string
  size?: AvatarSize
}

const sizeClasses: Record<AvatarSize, string> = {
  sm: 'size-8 text-xs',
  md: 'size-10 text-sm',
  lg: 'size-12 text-base',
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

/**
 * Round user avatar. Falls back to the user's initials when no image is
 * provided or the image fails to load, so it never renders a broken image.
 */
export function Avatar({ name, src, size = 'md' }: AvatarProps) {
  const [failed, setFailed] = useState(false)
  const showImage = Boolean(src) && !failed

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-brand-soft font-semibold text-brand ${sizeClasses[size]}`}
    >
      {showImage ? (
        <img
          src={src}
          alt={name}
          className="size-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <span role="img" aria-label={name}>
          {initials(name)}
        </span>
      )}
    </span>
  )
}
