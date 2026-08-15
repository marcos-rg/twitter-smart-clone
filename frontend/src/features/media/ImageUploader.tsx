import { useId, useRef } from 'react'
import { Button } from '../../components/ui'
import { ChevronLeftIcon, ChevronRightIcon, ImagePlusIcon } from '../../components/ui/icons'
import { useImageUploader, type UseImageUploaderOptions } from './useImageUploader'
import type { UploadItem } from './types'

export interface ImageUploaderProps extends UseImageUploaderOptions {
  /** Accessible label for the whole picker region. */
  label: string
}

function statusText(item: UploadItem): string {
  switch (item.status) {
    case 'uploading':
      return `Uploading… ${item.progress}%`
    case 'confirming':
      return 'Finishing…'
    case 'success':
      return 'Uploaded'
    case 'error':
      return item.errorMessage ?? 'Upload failed'
  }
}

/**
 * Reusable multi-image picker/uploader (tweet images, up to `maxFiles`).
 * Renders a preview grid with per-item progress, retry, remove, reorder
 * (keyboard-operable move-left/move-right, no drag-only affordance), and an
 * alt-text field per image. Validation runs before any network call and
 * invalid selections are announced via an `aria-live` region rather than
 * silently dropped. See `AvatarUploader` for the single-image variant used
 * on the profile-edit screen.
 */
export function ImageUploader({ label, ...options }: ImageUploaderProps) {
  const { items, rejections, addFiles, removeItem, retryItem, moveItem, setAltText } =
    useImageUploader(options)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const atMax = items.length >= options.maxFiles

  return (
    <div className="flex flex-col gap-3" role="group" aria-label={label}>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple={options.maxFiles > 1}
        className="sr-only"
        aria-label={label}
        onChange={(event) => {
          if (event.target.files) addFiles(event.target.files)
          event.target.value = ''
        }}
      />
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={atMax}
          onClick={() => inputRef.current?.click()}
        >
          <ImagePlusIcon className="size-4" />
          {items.length === 0 ? 'Add images' : 'Add more images'}
        </Button>
        <p className="mt-1 text-xs text-muted">
          PNG, JPEG, or WEBP. Up to {options.maxFiles} image{options.maxFiles === 1 ? '' : 's'}, 5
          MB each.
        </p>
      </div>

      {rejections.length > 0 ? (
        <ul
          role="alert"
          className="flex flex-col gap-1 rounded-control border border-danger bg-danger/10 p-3 text-sm text-danger"
        >
          {rejections.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {items.length > 0 ? (
        <ul id={listId} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {items.map((item, index) => (
            <li key={item.id} className="flex flex-col gap-2 rounded-card border border-border p-2">
              <div className="relative aspect-square overflow-hidden rounded-control bg-surface">
                <img
                  src={item.previewUrl}
                  alt={item.altText || 'Image preview'}
                  className="size-full object-cover"
                />
                {item.status === 'uploading' || item.status === 'confirming' ? (
                  <div className="absolute inset-x-0 bottom-0 h-1.5 bg-black/20">
                    <div
                      className="h-full bg-brand transition-[width] duration-150 motion-reduce:transition-none"
                      style={{ width: `${item.status === 'confirming' ? 100 : item.progress}%` }}
                    />
                  </div>
                ) : null}
              </div>
              <p
                className={`text-xs ${item.status === 'error' ? 'text-danger' : 'text-muted'}`}
                role={item.status === 'error' ? 'alert' : undefined}
              >
                {statusText(item)}
              </p>
              <label className="flex flex-col gap-1 text-xs text-muted">
                Alt text
                <input
                  type="text"
                  value={item.altText}
                  onChange={(event) => setAltText(item.id, event.target.value)}
                  placeholder="Describe this image"
                  className="h-8 rounded-control border border-border bg-surface px-2 text-foreground"
                />
              </label>
              <div className="flex flex-wrap gap-1">
                {item.status === 'error' ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => retryItem(item.id)}
                  >
                    Retry
                  </Button>
                ) : null}
                <Button type="button" size="sm" variant="ghost" onClick={() => removeItem(item.id)}>
                  Remove
                </Button>
                {options.maxFiles > 1 ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      aria-label={`Move image ${index + 1} earlier`}
                      disabled={index === 0}
                      onClick={() => moveItem(item.id, -1)}
                    >
                      <ChevronLeftIcon className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      aria-label={`Move image ${index + 1} later`}
                      disabled={index === items.length - 1}
                      onClick={() => moveItem(item.id, 1)}
                    >
                      <ChevronRightIcon className="size-4" />
                    </Button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
