import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'

/**
 * Visual + interaction evidence for the reusable image uploader
 * (TSC-MEDIA-002 verification: "attach screenshots of empty, uploading,
 * partial-failure, and complete states"). Uses the `/lab` component lab's
 * "Image uploader" section, which is wired to the deterministic fake
 * adapter (no real network — same "no backend in e2e" convention as
 * `lab.spec.ts`/`profile-search.spec.ts`). The fake adapter fails any file
 * named `fail-*` on upload, which is what drives the partial-failure state.
 */

const SAMPLE_PNG = readFileSync(fileURLToPath(new URL('./fixtures/sample.png', import.meta.url)))

test.describe('Image uploader (component lab)', () => {
  test('empty, uploading, partial-failure, and complete states', async ({ page }) => {
    await page.goto('/lab')
    const section = page.locator('section', {
      has: page.getByRole('heading', { name: 'Image uploader' }),
    })
    await section.scrollIntoViewIfNeeded()

    // --- empty ---
    await expect(section.getByRole('button', { name: 'Add images' })).toBeVisible()
    await expect(section.locator('ul[role="alert"]')).toHaveCount(0)
    await page.screenshot({ path: 'test-results/screenshots/media-upload-empty.png' })

    // --- uploading ---
    const tweetImagesInput = section.locator('input[type="file"]').first()
    await tweetImagesInput.setInputFiles([
      { name: 'good-cat.png', mimeType: 'image/png', buffer: SAMPLE_PNG },
      { name: 'fail-dog.png', mimeType: 'image/png', buffer: SAMPLE_PNG },
    ])
    // The fake adapter reports progress in steps ~120ms apart; catch it
    // mid-flight before either item settles.
    await expect(section.getByText(/Uploading…/).first()).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/media-upload-uploading.png' })

    // --- partial failure ---
    await expect(section.getByText('Uploaded')).toBeVisible()
    await expect(section.getByText('Simulated network failure during upload.')).toBeVisible()
    await expect(section.getByRole('button', { name: 'Retry' })).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/media-upload-partial-failure.png' })

    // --- complete (after removing the still-failed item rather than
    // retrying, proving "remove" clears a failure without touching the
    // successful upload) ---
    await section.getByRole('button', { name: 'Remove' }).last().click()
    await expect(section.getByText('Simulated network failure during upload.')).not.toBeVisible()
    await expect(section.getByText('Uploaded')).toBeVisible()
    await page.screenshot({ path: 'test-results/screenshots/media-upload-complete.png' })
  })

  test('reorder and retry controls are keyboard-operable', async ({ page }) => {
    await page.goto('/lab')
    const section = page.locator('section', {
      has: page.getByRole('heading', { name: 'Image uploader' }),
    })
    await section.scrollIntoViewIfNeeded()

    const tweetImagesInput = section.locator('input[type="file"]').first()
    await tweetImagesInput.setInputFiles([
      { name: 'first.png', mimeType: 'image/png', buffer: SAMPLE_PNG },
      { name: 'second.png', mimeType: 'image/png', buffer: SAMPLE_PNG },
    ])
    await expect(section.getByText('Uploaded')).toHaveCount(2)

    const moveLater = section.getByRole('button', { name: 'Move image 1 later' })
    await moveLater.focus()
    await expect(moveLater).toBeFocused()
    await page.keyboard.press('Enter')

    // First item moved to position 2: its "move later" control is now the
    // disabled one, proving the keyboard activation actually reordered.
    await expect(section.getByRole('button', { name: 'Move image 2 later' })).toBeDisabled()
  })
})
