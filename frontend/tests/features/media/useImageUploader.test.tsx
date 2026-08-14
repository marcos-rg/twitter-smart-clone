import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useImageUploader } from '../../../src/features/media/useImageUploader'
import type { MediaUploadAdapter } from '../../../src/features/media/types'

/**
 * Unit tests for the uploader state machine (TSC-MEDIA-002). Uses a fully
 * controllable in-memory adapter (no MSW/network) so upload outcomes,
 * ordering, and retry behavior are deterministic — the acceptance criteria
 * these cover ("confirmed keys in the approved order", "partial failure
 * supports retry ... without duplicating successful uploads", "temporary
 * object URLs are revoked") depend on exact call counts and ordering that
 * are easiest to assert against a fake adapter directly.
 */

function makeFile(name: string, type = 'image/png', size = 1024): File {
  return new File([new Uint8Array(size)], name, { type })
}

function makeControllableAdapter() {
  const presignCalls: string[] = []
  const confirmCalls: string[] = []
  const shouldFail = new Set<string>()

  const adapter: MediaUploadAdapter = {
    async presignOne(_purpose, file) {
      presignCalls.push(file.name)
      return {
        key: `tweet_image/user-1/${file.name}`,
        upload_url: `https://upload.test/${file.name}`,
        content_type: file.type,
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      }
    },
    async putObject(_url, file, onProgress) {
      onProgress(50)
      if (shouldFail.has(file.name)) {
        throw new Error(`Simulated failure for ${file.name}`)
      }
      onProgress(100)
    },
    async confirmOne(purpose, key, file) {
      confirmCalls.push(file.name)
      return { key, content_type: file.type, size_bytes: file.size }
    },
  }

  return { adapter, presignCalls, confirmCalls, shouldFail }
}

describe('useImageUploader', () => {
  it('uploads valid files and reports confirmed keys in the order they were added', async () => {
    const { adapter } = makeControllableAdapter()
    const onConfirmedKeysChange = vi.fn()
    const { result } = renderHook(() =>
      useImageUploader({ purpose: 'tweet_image', maxFiles: 4, adapter, onConfirmedKeysChange }),
    )

    act(() => {
      result.current.addFiles([makeFile('zebra.png'), makeFile('apple.png')])
    })

    await waitFor(() => expect(result.current.items.every((i) => i.status === 'success')).toBe(true))

    // Order matches selection order (zebra, then apple), not alphabetical or
    // network-completion order.
    expect(result.current.items.map((i) => i.file.name)).toEqual(['zebra.png', 'apple.png'])
    const lastCall = onConfirmedKeysChange.mock.calls.at(-1)?.[0]
    expect(lastCall).toEqual(['tweet_image/user-1/zebra.png', 'tweet_image/user-1/apple.png'])
  })

  it('rejects invalid type/size/count before any network call, with reasons exposed for accessible feedback', () => {
    const { adapter, presignCalls } = makeControllableAdapter()
    const { result } = renderHook(() => useImageUploader({ purpose: 'tweet_image', maxFiles: 2, adapter }))

    act(() => {
      result.current.addFiles([
        makeFile('doc.pdf', 'application/pdf'),
        makeFile('huge.png', 'image/png', 10 * 1024 * 1024),
      ])
    })

    expect(result.current.items).toHaveLength(0)
    expect(presignCalls).toHaveLength(0)
    expect(result.current.rejections).toHaveLength(2)
    expect(result.current.rejections[0]).toMatch(/not a supported image type/)
    expect(result.current.rejections[1]).toMatch(/too large/)
  })

  it('rejects a selection that exceeds maxFiles without uploading the overflow', () => {
    const { adapter, presignCalls } = makeControllableAdapter()
    const { result } = renderHook(() => useImageUploader({ purpose: 'tweet_image', maxFiles: 2, adapter }))

    act(() => {
      result.current.addFiles([makeFile('a.png'), makeFile('b.png'), makeFile('c.png')])
    })

    expect(result.current.items).toHaveLength(2)
    expect(presignCalls).toEqual(['a.png', 'b.png'])
    expect(result.current.rejections.some((r) => r.includes('max 2'))).toBe(true)
  })

  it('retrying a failed item does not duplicate or re-upload the already-successful ones', async () => {
    const { adapter, presignCalls, confirmCalls, shouldFail } = makeControllableAdapter()
    shouldFail.add('broken.png')
    const { result } = renderHook(() => useImageUploader({ purpose: 'tweet_image', maxFiles: 4, adapter }))

    act(() => {
      result.current.addFiles([makeFile('good.png'), makeFile('broken.png')])
    })

    await waitFor(() => {
      const good = result.current.items.find((i) => i.file.name === 'good.png')
      const broken = result.current.items.find((i) => i.file.name === 'broken.png')
      expect(good?.status).toBe('success')
      expect(broken?.status).toBe('error')
    })
    expect(presignCalls).toEqual(['good.png', 'broken.png'])
    expect(confirmCalls).toEqual(['good.png'])

    shouldFail.delete('broken.png')
    const brokenId = result.current.items.find((i) => i.file.name === 'broken.png')!.id
    act(() => {
      result.current.retryItem(brokenId)
    })

    await waitFor(() => {
      expect(result.current.items.find((i) => i.id === brokenId)?.status).toBe('success')
    })

    // "good.png" was never re-presigned/re-confirmed by the retry.
    expect(presignCalls.filter((n) => n === 'good.png')).toHaveLength(1)
    expect(confirmCalls.filter((n) => n === 'good.png')).toHaveLength(1)
    expect(presignCalls.filter((n) => n === 'broken.png')).toHaveLength(2)
    expect(result.current.items.every((i) => i.status === 'success')).toBe(true)
  })

  it('removing an item revokes its object URL and drops it from the confirmed list without touching others', async () => {
    const { adapter } = makeControllableAdapter()
    const onConfirmedKeysChange = vi.fn()
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')
    const { result } = renderHook(() =>
      useImageUploader({ purpose: 'tweet_image', maxFiles: 4, adapter, onConfirmedKeysChange }),
    )

    act(() => {
      result.current.addFiles([makeFile('one.png'), makeFile('two.png')])
    })
    await waitFor(() => expect(result.current.items.every((i) => i.status === 'success')).toBe(true))

    const oneId = result.current.items.find((i) => i.file.name === 'one.png')!.id
    const oneUrl = result.current.items.find((i) => i.file.name === 'one.png')!.previewUrl

    act(() => {
      result.current.removeItem(oneId)
    })

    expect(revokeSpy).toHaveBeenCalledWith(oneUrl)
    expect(result.current.items.map((i) => i.file.name)).toEqual(['two.png'])
    expect(onConfirmedKeysChange).toHaveBeenLastCalledWith(['tweet_image/user-1/two.png'])
    revokeSpy.mockRestore()
  })

  it('revokes every remaining object URL on unmount', async () => {
    const { adapter } = makeControllableAdapter()
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')
    const { result, unmount } = renderHook(() =>
      useImageUploader({ purpose: 'tweet_image', maxFiles: 4, adapter }),
    )

    act(() => {
      result.current.addFiles([makeFile('one.png'), makeFile('two.png')])
    })
    await waitFor(() => expect(result.current.items).toHaveLength(2))
    const urls = result.current.items.map((i) => i.previewUrl)

    unmount()

    urls.forEach((url) => expect(revokeSpy).toHaveBeenCalledWith(url))
    revokeSpy.mockRestore()
  })

  it('replacing a single-file (avatar) selection revokes the previous preview URL', async () => {
    const { adapter } = makeControllableAdapter()
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')
    const { result } = renderHook(() => useImageUploader({ purpose: 'avatar', maxFiles: 1, adapter }))

    act(() => {
      result.current.addFiles([makeFile('first.png')])
    })
    await waitFor(() => expect(result.current.items[0]?.status).toBe('success'))
    const firstUrl = result.current.items[0].previewUrl

    act(() => {
      result.current.addFiles([makeFile('second.png')])
    })

    expect(revokeSpy).toHaveBeenCalledWith(firstUrl)
    expect(result.current.items).toHaveLength(1)
    expect(result.current.items[0].file.name).toBe('second.png')
    revokeSpy.mockRestore()
  })

  it('reorders items and reflects the new order in the confirmed-keys callback', async () => {
    const { adapter } = makeControllableAdapter()
    const onConfirmedKeysChange = vi.fn()
    const { result } = renderHook(() =>
      useImageUploader({ purpose: 'tweet_image', maxFiles: 4, adapter, onConfirmedKeysChange }),
    )

    act(() => {
      result.current.addFiles([makeFile('one.png'), makeFile('two.png')])
    })
    await waitFor(() => expect(result.current.items.every((i) => i.status === 'success')).toBe(true))

    const oneId = result.current.items.find((i) => i.file.name === 'one.png')!.id
    act(() => {
      result.current.moveItem(oneId, 1)
    })

    expect(result.current.items.map((i) => i.file.name)).toEqual(['two.png', 'one.png'])
    expect(onConfirmedKeysChange).toHaveBeenLastCalledWith([
      'tweet_image/user-1/two.png',
      'tweet_image/user-1/one.png',
    ])
  })
})
