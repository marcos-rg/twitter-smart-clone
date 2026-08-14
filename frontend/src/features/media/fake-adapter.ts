import type { MediaUploadAdapter } from './types'

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** In-memory fake adapter: no network calls. Simulates presign latency and
 * upload progress, and deterministically fails any file whose name starts
 * with `fail-` (so the lab and e2e screenshots can reliably reproduce the
 * partial-failure state without timing races). Used by the `/lab` component
 * lab; real screens always use `defaultMediaUploadAdapter` (tweet images) or
 * `AvatarUploader`'s own adapter (avatars).
 */
export function createFakeMediaUploadAdapter(): MediaUploadAdapter {
  return {
    async presignOne(_purpose, file) {
      await wait(150)
      return {
        key: `fake/${file.name}`,
        upload_url: 'about:blank',
        content_type: file.type,
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      }
    },
    async putObject(_uploadUrl, file, onProgress) {
      if (file.name.startsWith('fail-')) {
        await wait(300)
        onProgress(40)
        await wait(200)
        throw new Error('Simulated network failure during upload.')
      }
      for (const percent of [20, 45, 70, 100]) {
        await wait(120)
        onProgress(percent)
      }
    },
    async confirmOne(_purpose, key, file) {
      await wait(150)
      return { key, content_type: file.type, size_bytes: file.size }
    },
  }
}
