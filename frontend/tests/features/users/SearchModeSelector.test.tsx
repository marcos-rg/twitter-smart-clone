import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it, vi } from 'vitest'
import { SearchModeSelector } from '../../../src/features/users/SearchModeSelector'

describe('SearchModeSelector', () => {
  it('marks the current mode as checked and calls onChange on click', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SearchModeSelector value="prefix" onChange={onChange} />)

    expect(screen.getByRole('radio', { name: 'Prefix' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'Exact' })).toHaveAttribute('aria-checked', 'false')

    await user.click(screen.getByRole('radio', { name: 'Fuzzy' }))
    expect(onChange).toHaveBeenCalledWith('fuzzy')
  })

  it('supports arrow-key navigation between modes', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SearchModeSelector value="prefix" onChange={onChange} />)

    screen.getByRole('radio', { name: 'Prefix' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenCalledWith('exact')

    await user.keyboard('{Home}')
    expect(onChange).toHaveBeenLastCalledWith('prefix')

    await user.keyboard('{End}')
    expect(onChange).toHaveBeenLastCalledWith('fuzzy')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SearchModeSelector value="exact" onChange={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
