import { resolveMediaUrl } from '../../api/media'
import type { TweetMediaOut } from '../../api/types'

export interface TweetImageGalleryProps {
  media: TweetMediaOut[]
}

/**
 * Responsive image grid for a tweet's 0-4 attached images (spec §5.1
 * `tweet_media`, `position` 0-3). There is no alt-text field on
 * `TweetMediaOut` — the backend only returns `key`/`content_type`/`position`
 * — so each image gets a positional fallback alt (`"Tweet image N"`) rather
 * than inventing a field the API doesn't provide.
 *
 * Layout: 1 image is full width; 2 are side-by-side columns; 3 puts the
 * first image large on the left with the remaining two stacked on the
 * right; 4 is a 2x2 grid.
 */
export function TweetImageGallery({ media }: TweetImageGalleryProps) {
  if (media.length === 0) return null

  const ordered = [...media].sort((a, b) => a.position - b.position)
  const count = ordered.length

  return (
    <div
      className={`mt-2 grid gap-1 overflow-hidden rounded-card border border-border ${
        count === 1 ? 'grid-cols-1' : 'grid-cols-2'
      }`}
    >
      {ordered.map((item, index) => (
        <img
          key={item.key}
          src={resolveMediaUrl(item.key)}
          alt={`Tweet image ${index + 1}`}
          className={`h-full max-h-96 w-full bg-surface object-cover ${
            count === 1 ? 'max-h-[32rem]' : ''
          } ${count === 3 && index === 0 ? 'row-span-2' : ''}`}
        />
      ))}
    </div>
  )
}
