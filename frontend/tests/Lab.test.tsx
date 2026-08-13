import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ToastProvider } from '../src/components/ui'
import { Lab } from '../src/routes/Lab'

function setup() {
  return render(
    <ToastProvider>
      <MemoryRouter>
        <Lab />
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('Design Lab route', () => {
  it('renders every component section', () => {
    setup()
    for (const section of [
      'Button',
      'Input',
      'Textarea',
      'Avatar',
      'Modal',
      'Toast',
      'Skeleton',
      'Tabs',
      'Tweet card',
      'Empty & error states',
    ]) {
      expect(screen.getByRole('heading', { name: section })).toBeInTheDocument()
    }
  })

  it('renders representative states: loading, disabled, error, empty, long content', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Loading' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Disabled' })).toBeDisabled()
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0) // input/textarea errors + ErrorState
    expect(screen.getByText('No tweets yet')).toBeInTheDocument()
    expect(screen.getByText(/intentionally long tweet/)).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Loading tweet' })).toBeInTheDocument()
  })

  it('opens and closes the modal example with the keyboard', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: 'Open modal' }))
    expect(screen.getByRole('dialog', { name: 'Example modal' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows a toast when a toast example is triggered', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: 'Info' }))
    // Other labelled Skeletons on the page also use role=status; find the toast.
    const statuses = screen.getAllByRole('status')
    expect(statuses.some((el) => el.textContent?.includes('Tweet posted.'))).toBe(true)
  })

  it('has no accessibility violations', async () => {
    const { container } = setup()
    expect(await axe(container)).toHaveNoViolations()
  })
})
