import { render, screen } from '@testing-library/react'
import { axe } from 'jest-axe'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppShell } from '../../src/components/layout/AppShell'
import { useAuthStore } from '../../src/stores/auth-store'
import { useNotificationsStore } from '../../src/stores/notifications-store'

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

  describe('notifications nav item', () => {
    afterEach(() => {
      useAuthStore.setState({
        accessToken: null,
        user: null,
        status: 'idle',
        sessionExpired: false,
      })
      useNotificationsStore.getState().reset()
    })

    it('is hidden while unauthenticated', () => {
      setup()
      expect(screen.queryByRole('link', { name: /notifications/i })).not.toBeInTheDocument()
    })

    it('shows an unread-count badge once signed in with unread notifications', () => {
      useAuthStore.setState({
        accessToken: 'tok',
        user: {
          id: 'user-1',
          name: 'Ada Lovelace',
          username: 'ada',
          email: 'ada@example.com',
          bio: null,
          avatar_key: null,
          created_at: '2026-01-01T00:00:00Z',
        },
        status: 'authenticated',
        sessionExpired: false,
      })
      useNotificationsStore.getState().setUnreadCount(3)

      setup()

      const links = screen.getAllByRole('link', { name: /notifications, 3 unread/i })
      expect(links.length).toBeGreaterThan(0)
    })
  })
})
