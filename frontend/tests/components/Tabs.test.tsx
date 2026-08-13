import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { Tabs } from '../../src/components/ui/Tabs'

const tabs = [
  { id: 'one', label: 'First', content: <p>Panel one</p> },
  { id: 'two', label: 'Second', content: <p>Panel two</p> },
  { id: 'three', label: 'Third', content: <p>Panel three</p> },
]

function setup(props: Partial<Parameters<typeof Tabs>[0]> = {}) {
  return render(<Tabs aria-label="Demo tabs" tabs={tabs} {...props} />)
}

describe('Tabs', () => {
  it('renders tablist, tabs, and panels with ARIA wiring', () => {
    setup()
    expect(screen.getByRole('tablist', { name: 'Demo tabs' })).toBeInTheDocument()
    const first = screen.getByRole('tab', { name: 'First' })
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveAttribute('aria-selected', 'false')
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveTextContent('Panel one')
    expect(panel).toHaveAttribute('aria-labelledby', first.id)
    expect(first).toHaveAttribute('aria-controls', panel.id)
  })

  it('uses roving tabindex: only the active tab is tabbable', () => {
    setup()
    expect(screen.getByRole('tab', { name: 'First' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveAttribute('tabindex', '-1')
  })

  it('arrow keys move and select tabs (automatic activation)', async () => {
    const user = userEvent.setup()
    setup()
    const first = screen.getByRole('tab', { name: 'First' })
    first.focus()

    await user.keyboard('{ArrowRight}')
    const second = screen.getByRole('tab', { name: 'Second' })
    expect(second).toHaveFocus()
    expect(second).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel two')

    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Third' })).toHaveFocus()

    await user.keyboard('{ArrowRight}') // wraps around
    expect(first).toHaveFocus()

    await user.keyboard('{ArrowLeft}') // wraps backwards
    expect(screen.getByRole('tab', { name: 'Third' })).toHaveFocus()
  })

  it('Home and End jump to the first and last tab', async () => {
    const user = userEvent.setup()
    setup()
    screen.getByRole('tab', { name: 'First' }).focus()
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Third' })).toHaveFocus()
    await user.keyboard('{Home}')
    expect(screen.getByRole('tab', { name: 'First' })).toHaveFocus()
  })

  it('selects a tab on click', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('tab', { name: 'Second' }))
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel two')
  })

  it('skips disabled tabs during keyboard navigation', async () => {
    const user = userEvent.setup()
    setup({
      tabs: [tabs[0], { id: 'disabled', label: 'Nope', content: null, disabled: true }, tabs[1]],
    })
    expect(screen.getByRole('tab', { name: 'Nope' })).toBeDisabled()
    screen.getByRole('tab', { name: 'First' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveFocus()
  })

  it('honours defaultTab', () => {
    setup({ defaultTab: 'two' })
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveAttribute('aria-selected', 'true')
  })

  it('has no accessibility violations', async () => {
    const { container } = setup()
    expect(await axe(container)).toHaveNoViolations()
  })
})
