import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../src/components/ui/Toast'
import { useToast } from '../../src/components/ui/toast-context'

function ToastTrigger({ variant }: { variant?: 'info' | 'success' | 'error' }) {
  const { toast } = useToast()
  return (
    <button type="button" onClick={() => toast('Hello there', variant)}>
      Notify
    </button>
  )
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a polite status toast and auto-dismisses it', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Notify' }))
    expect(screen.getByRole('status')).toHaveTextContent('Hello there')

    act(() => vi.advanceTimersByTime(6000))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('uses role=alert for error toasts', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(
      <ToastProvider>
        <ToastTrigger variant="error" />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Notify' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Hello there')
  })

  it('dismisses a toast via its dismiss button', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(
      <ToastProvider>
        <ToastTrigger variant="success" />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Notify' }))
    await user.click(screen.getByRole('button', { name: 'Dismiss notification' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('throws when useToast is used outside the provider', () => {
    function Orphan() {
      useToast()
      return null
    }
    expect(() => render(<Orphan />)).toThrow(/within a ToastProvider/)
  })

  it('has no accessibility violations', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const { container } = render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Notify' }))
    expect(await axe(container)).toHaveNoViolations()
  })
})
