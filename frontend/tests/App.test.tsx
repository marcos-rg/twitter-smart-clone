import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App'

describe('App', () => {
  it('renders the scaffold placeholder heading', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /twitter smart clone/i })).toBeInTheDocument()
  })
})
