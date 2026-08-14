import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { LoginForm } from '../../../src/features/auth/LoginForm'
import { server } from '../../mocks/server'
import { renderWithProviders } from '../../test-utils'

describe('LoginForm', () => {
  it('shows inline validation errors and does not submit invalid input', async () => {
    const user = userEvent.setup()
    const onSuccess = vi.fn()
    renderWithProviders(<LoginForm onSuccess={onSuccess} />)

    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(screen.getByText('Email is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('is keyboard accessible: tab through fields and submit with Enter', async () => {
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({
          access_token: 'token-123',
          token_type: 'bearer',
          expires_in: 900,
          user: {
            id: 'user-1',
            name: 'Ada Lovelace',
            username: 'ada',
            email: 'ada@example.com',
            bio: null,
            avatar_key: null,
            created_at: '2026-01-01T00:00:00Z',
          },
        }),
      ),
    )
    const user = userEvent.setup()
    const onSuccess = vi.fn()
    renderWithProviders(<LoginForm onSuccess={onSuccess} />)

    await user.tab()
    expect(screen.getByLabelText('Email')).toHaveFocus()
    await user.keyboard('ada@example.com')
    await user.tab()
    expect(screen.getByLabelText('Password')).toHaveFocus()
    await user.keyboard('correct horse battery staple{Enter}')

    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
  })

  it('shows a toast on invalid credentials', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />)

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('Invalid email or password.')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithProviders(<LoginForm onSuccess={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
