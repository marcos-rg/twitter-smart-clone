import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { ImageUploader } from '../../../src/features/media/ImageUploader'
import type { MediaUploadAdapter } from '../../../src/features/media/types'

function makeFile(name: string, type = 'image/png', size = 1024): File {
  return new File([new Uint8Array(size)], name, { type })
}

/** Resolves uploads instantly except for files whose name starts with
 * `fail-`, which reject at the `putObject` step — used to reach the
 * partial-failure state deterministically. */
const partialFailureAdapter: MediaUploadAdapter = {
  async presignOne(_purpose, file) {
    return {
      key: `tweet_image/user-1/${file.name}`,
      upload_url: `https://upload.test/${file.name}`,
      content_type: file.type,
      expires_at: new Date(Date.now() + 300_000).toISOString(),
    }
  },
  async putObject(_url, file, onProgress) {
    onProgress(100)
    if (file.name.startsWith('fail-')) throw new Error('Simulated upload failure.')
  },
  async confirmOne(_purpose, key, file) {
    return { key, content_type: file.type, size_bytes: file.size }
  },
}

async function selectFiles(user: ReturnType<typeof userEvent.setup>, files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, files)
}

// `applyAccept: false` because user-event otherwise silently filters files
// against the input's `accept` attribute before firing `change` — the
// "invalid type" test needs the file to actually reach `addFiles` so the
// component's own (not the browser's) validation/rejection UI is exercised.
const permissiveUser = () => userEvent.setup({ applyAccept: false })

describe('ImageUploader', () => {
  it('is empty by default and shows the picker control', () => {
    render(
      <ImageUploader
        label="Tweet images"
        purpose="tweet_image"
        maxFiles={4}
        adapter={partialFailureAdapter}
      />,
    )
    expect(screen.getByRole('button', { name: 'Add images' })).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('rejects an invalid file before upload and announces it accessibly', async () => {
    const user = permissiveUser()
    render(
      <ImageUploader
        label="Tweet images"
        purpose="tweet_image"
        maxFiles={4}
        adapter={partialFailureAdapter}
      />,
    )

    await selectFiles(user, [makeFile('resume.pdf', 'application/pdf')])

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/not a supported image type/)
    // Rejected files never become preview items.
    expect(screen.queryByAltText('Image preview')).not.toBeInTheDocument()
  })

  it('uploads valid files and reaches the complete state', async () => {
    const user = userEvent.setup()
    render(
      <ImageUploader
        label="Tweet images"
        purpose="tweet_image"
        maxFiles={4}
        adapter={partialFailureAdapter}
      />,
    )

    await selectFiles(user, [makeFile('cat.png')])

    await waitFor(() => expect(screen.getByText('Uploaded')).toBeInTheDocument())
  })

  it('shows a partial-failure state with retry, and retry recovers without touching the successful item', async () => {
    const user = userEvent.setup()
    render(
      <ImageUploader
        label="Tweet images"
        purpose="tweet_image"
        maxFiles={4}
        adapter={partialFailureAdapter}
      />,
    )

    await selectFiles(user, [makeFile('good.png'), makeFile('fail-bad.png')])

    await waitFor(() => expect(screen.getByText('Uploaded')).toBeInTheDocument())
    expect(await screen.findByText('Simulated upload failure.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('is keyboard operable: Tab reaches the picker and reorder controls, Enter/Space activates them', async () => {
    const user = userEvent.setup()
    render(
      <ImageUploader
        label="Tweet images"
        purpose="tweet_image"
        maxFiles={4}
        adapter={partialFailureAdapter}
      />,
    )

    await selectFiles(user, [makeFile('one.png'), makeFile('two.png')])
    await waitFor(() => expect(screen.getAllByText('Uploaded')).toHaveLength(2))

    const moveLater = screen.getByRole('button', { name: 'Move image 1 later' })
    moveLater.focus()
    expect(moveLater).toHaveFocus()
    await user.keyboard('{Enter}')

    // "one.png" moved from position 1 to position 2: its "move later" control
    // is now disabled (it's last) and "move earlier" is enabled.
    expect(screen.getByRole('button', { name: 'Move image 2 later' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move image 2 earlier' })).toBeEnabled()
  })

  it('has no accessibility violations in the partial-failure state', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <ImageUploader
        label="Tweet images"
        purpose="tweet_image"
        maxFiles={4}
        adapter={partialFailureAdapter}
      />,
    )

    await selectFiles(user, [makeFile('good.png'), makeFile('fail-bad.png')])
    await waitFor(() => expect(screen.getByText('Uploaded')).toBeInTheDocument())
    await screen.findByText('Simulated upload failure.')

    expect(await axe(container)).toHaveNoViolations()
  })
})
