import { useState, type FormEvent } from 'react'
import { Avatar, Button, Textarea, useToast } from '../../components/ui'
import { resolveMediaUrl } from '../../api/media'
import { useAuthStore } from '../../stores/auth-store'
import { ImageUploader } from '../media/ImageUploader'
import type { MediaUploadAdapter, UploadItem } from '../media/types'
import { describeTweetsError, useCreateTweet } from './hooks'

/** Mirrors `CONTENT_MAX_LENGTH` in `backend/app/models/tweet.py`. */
const CONTENT_MAX_LENGTH = 280
/** Danger-state threshold: warn once few characters remain. */
const WARNING_THRESHOLD = 20

export interface TweetComposerProps {
  /** Set when composing a reply — the id of the (always-root) tweet being
   * replied to. Omitted when composing a new root tweet. */
  parentTweetId?: string
  /** Set when posting a root tweet from a profile screen, so the new tweet
   * can be prepended to that profile's cached timeline without a refetch. */
  profileUsername?: string
  /** Set when posting a root tweet from the home feed, so the new tweet is
   * prepended to the cached feed without a refetch (TSC-FEED-002). */
  prependToFeed?: boolean
  placeholder?: string
  onPosted?: (tweetId: string) => void
  /** Overrides the embedded `ImageUploader`'s real presign/upload/confirm
   * adapter. Used by the component lab and tests to exercise the composer
   * without hitting the network. */
  imageUploadAdapter?: MediaUploadAdapter
}

/** Mirrors the backend's whitespace policy (`TweetCreateRequest._validate_content`,
 * `docs/tweet-backend.md`): leading/trailing whitespace is stripped before
 * counting/validating; the stripped content must have at least one
 * non-whitespace character; internal whitespace/newlines are untouched. */
function strippedLength(content: string): number {
  return content.trim().length
}

/**
 * Tweet composer: content textarea with a live character counter mirroring
 * the backend's whitespace/length rule, plus an embedded `ImageUploader`
 * (0-4 images). Reused for both "new root tweet" (profile screen,
 * `parentTweetId` omitted) and "reply" (tweet-detail screen, `parentTweetId`
 * set).
 *
 * On a recoverable failure (network error or 4xx/5xx), the typed content and
 * any in-progress/uploaded images are preserved — only a successful
 * `POST /tweets` clears the composer. The error is surfaced via a toast.
 */
export function TweetComposer({
  parentTweetId,
  profileUsername,
  prependToFeed,
  placeholder,
  onPosted,
  imageUploadAdapter,
}: TweetComposerProps) {
  const [content, setContent] = useState('')
  const [mediaKeys, setMediaKeys] = useState<string[]>([])
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([])
  const [uploaderResetKey, setUploaderResetKey] = useState(0)
  const { toast } = useToast()
  const mutation = useCreateTweet({ profileUsername, prependToFeed })
  const user = useAuthStore((state) => state.user)

  const isReply = Boolean(parentTweetId)
  const trimmedLength = strippedLength(content)
  const isBlank = trimmedLength === 0
  const overLimit = trimmedLength > CONTENT_MAX_LENGTH
  const remaining = CONTENT_MAX_LENGTH - trimmedLength
  const hasPendingUploads = uploadItems.some(
    (item) => item.status === 'uploading' || item.status === 'confirming',
  )
  const canSubmit = !isBlank && !overLimit && !hasPendingUploads && !mutation.isPending

  const counterClass = overLimit
    ? 'text-danger font-semibold'
    : remaining <= WARNING_THRESHOLD
      ? 'text-foreground font-semibold'
      : 'text-muted'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    try {
      const tweet = await mutation.mutateAsync({
        content,
        parent_tweet_id: parentTweetId ?? null,
        media_keys: mediaKeys,
      })
      setContent('')
      setMediaKeys([])
      setUploadItems([])
      setUploaderResetKey((key) => key + 1)
      onPosted?.(tweet.id)
    } catch (error) {
      toast(describeTweetsError(error), 'error')
    }
  }

  return (
    <form
      onSubmit={(event) => void handleSubmit(event)}
      aria-label={isReply ? 'Reply composer' : 'Tweet composer'}
      className="flex gap-3 border-b border-border px-4 py-4"
    >
      {/* Decorative: the signed-in user's identity is already established
          elsewhere on every screen that renders this composer (profile
          header, "Signed in as" link), so this avatar is hidden from the
          accessibility tree rather than exposing a second same-named image. */}
      <span aria-hidden="true">
        <Avatar name={user?.name ?? 'You'} src={resolveMediaUrl(user?.avatar_key)} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <Textarea
          label={isReply ? 'Post your reply' : "What's happening?"}
          hideLabel
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder={placeholder ?? (isReply ? 'Post your reply' : "What's happening?")}
          rows={2}
          className="border-transparent bg-transparent px-0 py-1 text-lg shadow-none placeholder:text-muted focus:border-transparent"
          error={
            overLimit
              ? `${trimmedLength - CONTENT_MAX_LENGTH} characters over the limit.`
              : undefined
          }
        />

        <ImageUploader
          key={uploaderResetKey}
          label="Add images to your tweet"
          purpose="tweet_image"
          maxFiles={4}
          adapter={imageUploadAdapter}
          onConfirmedKeysChange={setMediaKeys}
          onItemsChange={setUploadItems}
        />

        <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
          <span aria-live="polite" className={`text-sm ${counterClass}`}>
            {trimmedLength} / {CONTENT_MAX_LENGTH}
          </span>
          <Button type="submit" loading={mutation.isPending} disabled={!canSubmit}>
            {isReply ? 'Reply' : 'Post'}
          </Button>
        </div>
      </div>
    </form>
  )
}
