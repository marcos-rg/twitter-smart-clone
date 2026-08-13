import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App'

describe('App', () => {
  it('renders the home route inside the application shell', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /twitter smart clone/i })).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
  })

  it('renders the design lab at /lab', () => {
    window.history.pushState({}, '', '/lab')
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Design Lab' })).toBeInTheDocument()
  })
})
