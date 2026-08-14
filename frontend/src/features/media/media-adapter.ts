import {
  confirmOne as confirmMediaKey,
  presignOne as presignMediaFile,
  putObjectWithProgress,
} from '../../api/media'
import type { MediaUploadAdapter } from './types'

/** Default adapter: real presign → PUT → `/media/confirm`. Suitable for
 * tweet images. Avatars use their own adapter (see `AvatarUploader`) because
 * confirming an avatar is a different endpoint (`POST /users/me/avatar`)
 * that also has to update the cached signed-in user. */
export const defaultMediaUploadAdapter: MediaUploadAdapter = {
  presignOne: (purpose, file) =>
    presignMediaFile(purpose, { content_type: file.type, size_bytes: file.size }),
  putObject: putObjectWithProgress,
  confirmOne: (purpose, key) => confirmMediaKey(purpose, key),
}
