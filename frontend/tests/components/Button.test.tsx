import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it, vi } from 'vitest'
import { Button } from '../../src/components/ui/Button'

describe('Button', () => {
  it('renders all variants and sizes', () => {
    render(
      <>
        <Button>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="outline" size="sm">
          Outline small
        </Button>
        <Button variant="ghost" size="lg">
          Ghost large
        </Button>
        <Button variant="danger">Danger</Button>
      </>,
    )
    for (const name of ['Primary', 'Secondary', 'Outline small', 'Ghost large', 'Danger']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('calls onClick when activated by keyboard', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Save</Button>)
    screen.getByRole('button', { name: 'Save' }).focus()
    await user.keyboard('{Enter}')
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('is not interactive when disabled', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(
      <Button disabled onClick={onClick}>
        Disabled
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Disabled' })
    expect(button).toBeDisabled()
    await user.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows a spinner and aria-busy while loading', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Posting
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Posting' })
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toBeDisabled()
    await user.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Button>Default</Button>
        <Button loading>Loading</Button>
        <Button disabled>Disabled</Button>
      </>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
