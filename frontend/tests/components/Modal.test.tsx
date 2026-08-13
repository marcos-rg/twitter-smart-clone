import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from '../../src/components/ui/Button'
import { Modal } from '../../src/components/ui/Modal'

function ModalHarness() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Demo dialog">
        <button type="button">First action</button>
        <button type="button">Second action</button>
      </Modal>
    </>
  )
}

describe('Modal', () => {
  it('renders nothing when closed', () => {
    render(
      <Modal open={false} onClose={() => {}} title="Hidden">
        content
      </Modal>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders an accessible dialog labelled by its title', () => {
    render(
      <Modal open onClose={() => {}} title="Demo dialog">
        content
      </Modal>,
    )
    const dialog = screen.getByRole('dialog', { name: 'Demo dialog' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('moves focus into the dialog on open', async () => {
    const user = userEvent.setup()
    render(<ModalHarness />)
    await user.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByRole('button', { name: 'First action' })).toHaveFocus()
  })

  it('closes on Escape and restores focus to the trigger', async () => {
    const user = userEvent.setup()
    render(<ModalHarness />)
    const trigger = screen.getByRole('button', { name: 'Open' })
    await user.click(trigger)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('traps Tab within the dialog', async () => {
    const user = userEvent.setup()
    render(<ModalHarness />)
    await user.click(screen.getByRole('button', { name: 'Open' }))

    const first = screen.getByRole('button', { name: 'First action' })
    const second = screen.getByRole('button', { name: 'Second action' })
    expect(first).toHaveFocus()

    await user.tab()
    expect(second).toHaveFocus()
    await user.tab() // wraps to first
    expect(first).toHaveFocus()
    await user.tab({ shift: true }) // wraps backwards to last
    expect(second).toHaveFocus()
  })

  it('calls onClose when the backdrop is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <Modal open onClose={onClose} title="Demo dialog">
        content
      </Modal>,
    )
    const dialog = screen.getByRole('dialog')
    await user.click(dialog.parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Modal open onClose={() => {}} title="Demo dialog">
        <button type="button">Action</button>
      </Modal>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
