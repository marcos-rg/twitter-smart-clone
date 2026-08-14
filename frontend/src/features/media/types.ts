import type { ConfirmedMedia, MediaPurpose, PresignedUpload } from '../../api/types'

export type UploadItemStatus = 'uploading' | 'confirming' | 'success' | 'error'

/** One selected image's client-side upload state. `id` is a stable
 * client-generated identifier (independent of `confirmedKey`, which only
 * exists once the upload succeeds) used for React keys, removal, retry, and
 * reordering. */
export interface UploadItem {
  id: string
  file: File
  /** `URL.createObjectURL(file)` — revoked on removal/replace/unmount so it
   * never leaks (acceptance criterion). */
  previewUrl: string
  status: UploadItemStatus
  /** 0-100. Reflects `XMLHttpRequest.upload.onprogress` during `uploading`. */
  progress: number
  errorMessage?: string
  confirmedKey?: string
  /** User-editable alt text for the image (accessibility: every uploaded
   * image gets a describable label rather than a generic "image N"). */
  altText: string
}

/** Injectable seam between the reusable uploader and however a given variant
 * confirms a key server-side. Avatars and tweet images presign/PUT the same
 * way but confirm differently (`POST /users/me/avatar` vs. `POST
 * /media/confirm`) — `AvatarUploader` supplies a custom `confirmOne` that
 * also updates the signed-in user's cached profile, while the default
 * adapter below is enough for tweet images. Also what the component lab and
 * tests substitute with fakes to exercise progress/error states
 * deterministically without a real backend.
 */
export interface MediaUploadAdapter {
  presignOne(purpose: MediaPurpose, file: File): Promise<PresignedUpload>
  putObject(uploadUrl: string, file: File, onProgress: (percent: number) => void): Promise<void>
  confirmOne(purpose: MediaPurpose, key: string, file: File): Promise<ConfirmedMedia>
}
