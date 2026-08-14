import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../src/App'

describe('App', () => {
  it('redirects an unauthenticated visitor from "/" to the login screen', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())
  })

  it('renders the design lab at /lab regardless of auth state', () => {
    window.history.pushState({}, '', '/lab')
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Design Lab' })).toBeInTheDocument()
  })
})
