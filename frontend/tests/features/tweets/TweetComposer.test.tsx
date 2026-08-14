import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { TweetComposer } from '../../../src/features/tweets/TweetComposer'
import type { MediaUploadAdapter } from '../../../src/features/media/types'
import { renderWithProviders } from '../../test-utils'
import { server } from '../../mocks/server'
import { testUser } from '../../mocks/handlers'

/**
 * Composer unit/integration tests (TSC-TWEET-002): the whitespace/character
 * counter contract, blank rejection, content preservation on a failed
 * submit, and posting with confirmed media keys.
 */

function makeFile(name: string, type = 'image/png', size = 1024): File {
  return new File([new Uint8Array(size)], name, { type })
}

/** Resolves every upload instantly and deterministically — no network. */
const instantAdapter: MediaUploadAdapter = {
  async presignOne(_purpose, file) {
    return {
      key: `tweet_image/user-1/${file.name}`,
      upload_url: `https://upload.test/${file.name}`,
      content_type: file.type,
      expires_at: new Date(Date.now() + 300_000).toISOString(),
    }
  },
  async putObject(_url, _file, onProgress) {
    onProgress(100)
  },
  async confirmOne(_purpose, key, file) {
    return { key, content_type: file.type, size_bytes: file.size }
  },
}

async function selectFiles(user: ReturnType<typeof userEvent.setup>, files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, files)
}

describe('TweetComposer', () => {
  it('shows a live character counter that mirrors the backend whitespace rule', async () => {
    const user = userEvent.setup()
    renderWithProviders(<TweetComposer />)
    const textarea = screen.getByLabelText("What's happening?")

    await user.type(textarea, '  hello  ')
    // Leading/trailing whitespace is stripped before counting ("hello" = 5).
    expect(screen.getByText('5 / 280')).toBeInTheDocument()
  })

  it('disables submit for blank or whitespace-only content', async () => {
    const user = userEvent.setup()
    renderWithProviders(<TweetComposer />)
    const submit = screen.getByRole('button', { name: 'Post' })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText("What's happening?"), '    ')
    expect(submit).toBeDisabled()
  })

  it('disables submit and shows an over-limit error past 280 stripped characters', async () => {
    const user = userEvent.setup()
    renderWithProviders(<TweetComposer />)
    const textarea = screen.getByLabelText("What's happening?")
    await user.type(textarea, 'a'.repeat(281))

    expect(screen.getByText('281 / 280')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Post' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('1 characters over the limit.')
  })

  it('preserves typed content and shows a toast when the submit fails', async () => {
    server.use(
      http.post('*/api/v1/tweets', () =>
        HttpResponse.json(
          { error: { code: 'internal_error', message: 'Something broke on the server.' } },
          { status: 500 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<TweetComposer />)
    const textarea = screen.getByLabelText("What's happening?")
    await user.type(textarea, 'this should survive a failure')
    await user.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByText('Something broke on the server.')).toBeInTheDocument()
    expect(textarea).toHaveValue('this should survive a failure')
  })

  it('submits with the confirmed media_keys in upload order and clears on success', async () => {
    let capturedBody: Record<string, unknown> | undefined
    server.use(
      http.post('*/api/v1/tweets', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 'tweet-posted',
            author: {
              id: testUser.id,
              username: testUser.username,
              name: testUser.name,
              avatar_key: null,
            },
            content: (capturedBody.content as string).trim(),
            parent_tweet_id: null,
            like_count: 0,
            reply_count: 0,
            liked_by_viewer: false,
            media: (capturedBody.media_keys as string[]).map((key, position) => ({
              key,
              content_type: 'image/png',
              position,
            })),
            links: [],
            created_at: '2026-02-01T00:00:00Z',
          },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<TweetComposer imageUploadAdapter={instantAdapter} />)

    await user.type(screen.getByLabelText("What's happening?"), 'a tweet with an image')
    await selectFiles(user, [makeFile('cat.png')])

    await waitFor(() => expect(screen.getByText('Uploaded')).toBeInTheDocument())

    const submit = screen.getByRole('button', { name: 'Post' })
    await waitFor(() => expect(submit).not.toBeDisabled())
    await user.click(submit)

    await waitFor(() => expect(capturedBody).toBeDefined())
    expect(capturedBody?.media_keys).toEqual(['tweet_image/user-1/cat.png'])
    expect(screen.getByLabelText("What's happening?")).toHaveValue('')
  })
})
