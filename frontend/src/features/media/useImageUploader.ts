import { useCallback, useEffect, useRef, useState } from 'react'
import { ALLOWED_IMAGE_CONTENT_TYPES, MAX_IMAGE_BYTES } from '../../api/media'
import type { MediaPurpose } from '../../api/types'
import { ApiError } from '../../api/client'
import { defaultMediaUploadAdapter } from './media-adapter'
import type { MediaUploadAdapter, UploadItem } from './types'

export interface UseImageUploaderOptions {
  purpose: MediaPurpose
  /** 1 for avatars, up to `MAX_TWEET_IMAGES` for tweet images. When 1, a
   * newly-added valid file replaces (rather than appends to) the current
   * selection — there is only ever one avatar. */
  maxFiles: number
  adapter?: MediaUploadAdapter
  /** Called whenever the ordered list of successfully confirmed keys
   * changes — the "approved order" a caller (e.g. a tweet composer) should
   * submit. Order always matches the on-screen item order, independent of
   * which upload happened to finish first. */
  onConfirmedKeysChange?: (keys: string[]) => void
}

function describeUploadError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Upload failed. Check your connection and try again.'
}

function validateFile(file: File): string | null {
  if (
    !ALLOWED_IMAGE_CONTENT_TYPES.includes(file.type as (typeof ALLOWED_IMAGE_CONTENT_TYPES)[number])
  ) {
    return `"${file.name}" is not a supported image type. Use PNG, JPEG, or WEBP.`
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return `"${file.name}" is too large. The limit is ${Math.floor(MAX_IMAGE_BYTES / (1024 * 1024))} MB.`
  }
  return null
}

function patchItem(items: UploadItem[], id: string, patch: Partial<UploadItem>): UploadItem[] {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item))
}

function createId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `upload-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/**
 * Client-side state machine behind the reusable image uploader (TSC-MEDIA-002).
 * Owns: validation before any network call, per-item presign → PUT →
 * confirm, progress, retry/removal, reordering, alt text, and object-URL
 * cleanup. Deliberately upload/confirm-per-item (never batched) so retrying
 * one failed item can never re-upload or duplicate an already-successful one.
 */
export function useImageUploader({
  purpose,
  maxFiles,
  adapter = defaultMediaUploadAdapter,
  onConfirmedKeysChange,
}: UseImageUploaderOptions) {
  const [items, setItems] = useState<UploadItem[]>([])
  const [rejections, setRejections] = useState<string[]>([])
  const itemsRef = useRef<UploadItem[]>(items)
  itemsRef.current = items

  // Revoke every remaining object URL on unmount (acceptance criterion:
  // "temporary object URLs are revoked when replaced or unmounted").
  useEffect(() => {
    return () => {
      itemsRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    }
  }, [])

  useEffect(() => {
    onConfirmedKeysChange?.(
      items
        .filter((item) => item.status === 'success' && item.confirmedKey)
        .map((item) => item.confirmedKey as string),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onConfirmedKeysChange identity is not part of the dependency contract; only item state should retrigger this.
  }, [items])

  const runUpload = useCallback(
    async (item: UploadItem) => {
      setItems((prev) =>
        patchItem(prev, item.id, { status: 'uploading', progress: 0, errorMessage: undefined }),
      )
      try {
        const presigned = await adapter.presignOne(purpose, item.file)
        await adapter.putObject(presigned.upload_url, item.file, (percent) => {
          setItems((prev) => patchItem(prev, item.id, { progress: percent }))
        })
        setItems((prev) => patchItem(prev, item.id, { status: 'confirming', progress: 100 }))
        const confirmed = await adapter.confirmOne(purpose, presigned.key, item.file)
        setItems((prev) =>
          patchItem(prev, item.id, { status: 'success', confirmedKey: confirmed.key }),
        )
      } catch (error) {
        setItems((prev) =>
          patchItem(prev, item.id, { status: 'error', errorMessage: describeUploadError(error) }),
        )
      }
    },
    [adapter, purpose],
  )

  const addFiles = useCallback(
    (fileList: FileList | File[]) => {
      const incoming = Array.from(fileList)
      const reasons: string[] = []
      const accepted: File[] = []

      for (const file of incoming) {
        const reason = validateFile(file)
        if (reason) {
          reasons.push(reason)
        } else {
          accepted.push(file)
        }
      }

      let allowed = accepted
      let replacing = false
      if (maxFiles === 1) {
        replacing = true
        allowed = accepted.slice(-1)
      } else {
        const room = Math.max(maxFiles - itemsRef.current.length, 0)
        if (accepted.length > room) {
          reasons.push(
            room === 0
              ? `Up to ${maxFiles} images are allowed; no more can be added.`
              : `Only ${room} more image(s) can be added (max ${maxFiles}).`,
          )
        }
        allowed = accepted.slice(0, room)
      }

      setRejections(reasons)

      const newItems: UploadItem[] = allowed.map((file) => ({
        id: createId(),
        file,
        previewUrl: URL.createObjectURL(file),
        status: 'uploading',
        progress: 0,
        altText: '',
      }))

      if (newItems.length === 0) return

      setItems((prev) => {
        if (replacing) {
          prev.forEach((item) => URL.revokeObjectURL(item.previewUrl))
          return newItems
        }
        return [...prev, ...newItems]
      })
      newItems.forEach((item) => {
        void runUpload(item)
      })
    },
    [maxFiles, runUpload],
  )

  const removeItem = useCallback((id: string) => {
    setItems((prev) => {
      const target = prev.find((item) => item.id === id)
      if (target) URL.revokeObjectURL(target.previewUrl)
      return prev.filter((item) => item.id !== id)
    })
  }, [])

  const retryItem = useCallback(
    (id: string) => {
      const item = itemsRef.current.find((entry) => entry.id === id)
      if (item) void runUpload(item)
    },
    [runUpload],
  )

  const moveItem = useCallback((id: string, direction: -1 | 1) => {
    setItems((prev) => {
      const index = prev.findIndex((item) => item.id === id)
      const targetIndex = index + direction
      if (index === -1 || targetIndex < 0 || targetIndex >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(index, 1)
      next.splice(targetIndex, 0, moved)
      return next
    })
  }, [])

  const setAltText = useCallback((id: string, altText: string) => {
    setItems((prev) => patchItem(prev, id, { altText }))
  }, [])

  const dismissRejections = useCallback(() => setRejections([]), [])

  return {
    items,
    rejections,
    addFiles,
    removeItem,
    retryItem,
    moveItem,
    setAltText,
    dismissRejections,
  }
}
