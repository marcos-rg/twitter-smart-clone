import { request } from './client'
import type { ConfirmedMedia, MediaPurpose, PresignedUpload } from './types'

const BASE = '/api/v1/media'

/** Content-types the backend accepts (kept in sync with
 * `app.models.tweet_media.ALLOWED_CONTENT_TYPES`, spec §8.4). */
export const ALLOWED_IMAGE_CONTENT_TYPES = ['image/png', 'image/jpeg', 'image/webp'] as const

/** Mirrors `Settings.media_max_image_bytes` (backend default, spec §8.4:
 * "max ~5MB each"). Client-side validation is a UX nicety, not the trust
 * boundary — the server re-validates every declared size at presign time. */
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024

/** Mirrors `Settings.media_max_tweet_images` (backend default). */
export const MAX_TWEET_IMAGES = 4

/** `POST /media/presign` for a single file. Real batches (many files, one
 * request) aren't needed client-side: each upload item in the reusable
 * uploader presigns/uploads/confirms independently, which is what makes
 * per-item retry safe (spec-driven acceptance criterion: "partial upload
 * failure supports retry ... without duplicating successful uploads"). */
export function presignOne(
  purpose: MediaPurpose,
  file: { content_type: string; size_bytes: number },
): Promise<PresignedUpload> {
  return request<{ uploads: PresignedUpload[] }>(`${BASE}/presign`, {
    method: 'POST',
    body: { purpose, files: [file] },
  }).then((res) => res.uploads[0])
}

/** `POST /media/confirm` for a single previously presigned key. */
export function confirmOne(purpose: MediaPurpose, key: string): Promise<ConfirmedMedia> {
  return request<{ media: ConfirmedMedia[] }>(`${BASE}/confirm`, {
    method: 'POST',
    body: { purpose, keys: [key] },
  }).then((res) => res.media[0])
}

/** Uploads raw bytes directly to the presigned MinIO/S3 URL (spec §8.4 step
 * 3: "client PUTs directly to storage" — the API never proxies image bytes).
 * Uses `XMLHttpRequest` rather than `fetch` because it's the only browser
 * primitive that reports upload progress, which the uploader UI needs.
 */
export function putObjectWithProgress(
  uploadUrl: string,
  file: File,
  onProgress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', uploadUrl)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
      } else {
        reject(new Error(`Upload failed (status ${xhr.status}).`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload.'))
    xhr.send(file)
  })
}

const DEFAULT_MEDIA_PUBLIC_BASE_URL = 'http://localhost:9000/twitter-smart-clone-media'

const MEDIA_PUBLIC_BASE_URL = (
  (import.meta.env.VITE_MEDIA_PUBLIC_BASE_URL as string | undefined) ??
  DEFAULT_MEDIA_PUBLIC_BASE_URL
).replace(/\/+$/, '')

/** Resolves a confirmed object key (e.g. `avatar_key`) to a browser-loadable
 * URL. The bucket is configured for anonymous read (see `minio-init` in
 * `docker-compose.yml`) so this needs no auth — matches how `<img src>` can't
 * carry an Authorization header anyway. Returns `undefined` for `null`/`""`
 * so callers can pass it straight through to `Avatar`'s optional `src`.
 */
export function resolveMediaUrl(key: string | null | undefined): string | undefined {
  if (!key) return undefined
  return `${MEDIA_PUBLIC_BASE_URL}/${key}`
}
