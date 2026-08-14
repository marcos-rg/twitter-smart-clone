import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it, vi } from 'vitest'
import { RegisterForm } from '../../../src/features/auth/RegisterForm'
import { renderWithProviders } from '../../test-utils'

describe('RegisterForm', () => {
  it('shows inline validation errors and does not submit invalid input', async () => {
    const user = userEvent.setup()
    const onSuccess = vi.fn()
    renderWithProviders(<RegisterForm onSuccess={onSuccess} />)

    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(screen.getByText('Name is required.')).toBeInTheDocument()
    expect(screen.getByText('Username is required.')).toBeInTheDocument()
    expect(screen.getByText('Email is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('rejects an invalid username without a round trip', async () => {
    const user = userEvent.setup()
    renderWithProviders(<RegisterForm onSuccess={vi.fn()} />)

    await user.type(screen.getByLabelText('Username'), 'a')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(
      screen.getByText('Username must be 3-30 characters: letters, numbers, and underscores only.'),
    ).toBeInTheDocument()
  })

  it('submits valid input and calls onSuccess with the email', async () => {
    const user = userEvent.setup()
    const onSuccess = vi.fn()
    renderWithProviders(<RegisterForm onSuccess={onSuccess} />)

    await user.type(screen.getByLabelText('Name'), 'Ada Lovelace')
    await user.type(screen.getByLabelText('Username'), 'ada')
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct horse battery staple')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('ada@example.com'))
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithProviders(<RegisterForm onSuccess={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
