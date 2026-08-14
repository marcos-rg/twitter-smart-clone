import { useMemo, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Avatar, Button } from '../../components/ui'
import { useAuthStore } from '../../stores/auth-store'
import { confirmMyAvatar } from '../../api/users'
import { resolveMediaUrl } from '../../api/media'
import { profileQueryKey } from '../users/hooks'
import { useImageUploader } from './useImageUploader'
import { defaultMediaUploadAdapter } from './media-adapter'
import type { MediaUploadAdapter } from './types'

export interface AvatarUploaderProps {
  /** Display name, used for the initials fallback and alt text. */
  name: string
  /** Overrides the real confirm-and-persist adapter. Used by the component
   * lab and tests to demonstrate progress/error states without hitting the
   * network or mutating the signed-in user. */
  adapter?: MediaUploadAdapter
}

/**
 * Single-image avatar picker/uploader for the profile-edit screen
 * (TSC-MEDIA-002). Confirming an avatar upload is a different endpoint from
 * tweet images (`POST /users/me/avatar`, spec: "confirm sets `avatar_key`"),
 * so this supplies its own `confirmOne` that both calls that endpoint and
 * updates the signed-in user's cached profile — the header/nav reflect the
 * new avatar immediately, and it's still there after a reload because it's
 * now persisted server-side.
 */
export function AvatarUploader({ name, adapter: adapterOverride }: AvatarUploaderProps) {
  const user = useAuthStore((state) => state.user)
  const setSession = useAuthStore((state) => state.setSession)
  const queryClient = useQueryClient()

  const realAdapter = useMemo<MediaUploadAdapter>(
    () => ({
      ...defaultMediaUploadAdapter,
      confirmOne: async (_purpose, key, file) => {
        const profile = await confirmMyAvatar(key)
        const accessToken = useAuthStore.getState().accessToken
        if (accessToken) setSession(accessToken, profile)
        queryClient.setQueryData(profileQueryKey(profile.username), profile)
        return { key: profile.avatar_key ?? key, content_type: file.type, size_bytes: file.size }
      },
    }),
    [setSession, queryClient],
  )

  const { items, rejections, addFiles, removeItem, retryItem } = useImageUploader({
    purpose: 'avatar',
    maxFiles: 1,
    adapter: adapterOverride ?? realAdapter,
  })
  const inputRef = useRef<HTMLInputElement>(null)
  const item = items[0]

  const previewSrc = item?.previewUrl ?? resolveMediaUrl(user?.avatar_key)
  const status = item?.status

  return (
    <div className="flex flex-col gap-2" role="group" aria-label="Avatar">
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        aria-label="Avatar"
        onChange={(event) => {
          if (event.target.files) addFiles(event.target.files)
          event.target.value = ''
        }}
      />
      <div className="flex items-center gap-4">
        <div className="relative">
          <Avatar name={name} src={previewSrc} size="lg" />
          {status === 'uploading' || status === 'confirming' ? (
            <span
              role="status"
              className="absolute -bottom-1 -right-1 rounded-full bg-canvas px-1 text-[10px] font-semibold text-brand"
            >
              {status === 'confirming' ? '…' : `${item.progress}%`}
            </span>
          ) : null}
        </div>
        <div className="flex flex-col gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
          >
            Change avatar
          </Button>
          {item?.status === 'error' ? (
            <div className="flex items-center gap-2">
              <p role="alert" className="text-xs text-danger">
                {item.errorMessage}
              </p>
              <Button type="button" size="sm" variant="ghost" onClick={() => retryItem(item.id)}>
                Retry
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => removeItem(item.id)}>
                Remove
              </Button>
            </div>
          ) : (
            <p className="text-xs text-muted">PNG, JPEG, or WEBP. Up to 5 MB.</p>
          )}
        </div>
      </div>
      {rejections.length > 0 ? (
        <ul
          role="alert"
          className="flex flex-col gap-1 rounded-control border border-danger bg-danger/10 p-2 text-xs text-danger"
        >
          {rejections.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
