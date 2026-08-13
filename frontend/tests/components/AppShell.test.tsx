import { render, screen } from '@testing-library/react'
import { axe } from 'jest-axe'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AppShell } from '../../src/components/layout/AppShell'

function setup(route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AppShell>
        <p>Page content</p>
      </AppShell>
    </MemoryRouter>,
  )
}

describe('AppShell', () => {
  it('renders children inside the main landmark', () => {
    setup()
    expect(screen.getByRole('main')).toHaveTextContent('Page content')
  })

  it('provides a skip link to the main content', () => {
    setup()
    const skipLink = screen.getByRole('link', { name: 'Skip to main content' })
    expect(skipLink).toHaveAttribute('href', '#main-content')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
  })

  it('renders uniquely labelled navigation landmarks for desktop and mobile', () => {
    setup()
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Primary mobile' })).toBeInTheDocument()
  })

  it('marks the current route as active', () => {
    setup('/lab')
    const labLinks = screen.getAllByRole('link', { name: /design lab/i })
    expect(labLinks.some((link) => link.getAttribute('aria-current') === 'page')).toBe(true)
  })

  it('has no accessibility violations', async () => {
    const { container } = setup()
    expect(await axe(container)).toHaveNoViolations()
  })
})
