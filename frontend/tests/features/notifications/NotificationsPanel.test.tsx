import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { NotificationsPanel } from '../../../src/features/notifications/NotificationsPanel'
import { useNotificationsStore } from '../../../src/stores/notifications-store'
import { renderWithProviders } from '../../test-utils'
import { server } from '../../mocks/server'

/**
 * UI-level tests for the notifications panel (TSC-NOTIF-002): loading,
 * error, empty, and populated states, cursor pagination, and the
 * mark-selected/mark-all read actions including their keyboard
 * operability. Cache/de-duplication mechanics are unit-tested directly in
 * `hooks.test.tsx`; this file only exercises what a rendered panel actually
 * shows and does.
 */

function actor(overrides: Record<string, unknown> = {}) {
  return { id: 'user-2', username: 'grace', name: 'Grace Hopper', avatar_key: null, ...overrides }
}

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 'notif-1',
    type: 'like',
    actor: actor(),
    tweet_id: 'tweet-1',
    is_read: false,
    created_at: '2026-08-14T00:00:00Z',
    ...overrides,
  }
}

describe('NotificationsPanel', () => {
  beforeEach(() => {
    useNotificationsStore.getState().reset()
  })

  afterEach(() => {
    useNotificationsStore.getState().reset()
  })

  it('shows loading skeletons, then an empty state when there are no notifications', async () => {
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null }, unread_count: 0 }),
      ),
    )
    renderWithProviders(<NotificationsPanel />)

    expect(screen.getAllByRole('status', { name: 'Loading notification' }).length).toBeGreaterThan(
      0,
    )
    expect(await screen.findByText('No notifications yet')).toBeInTheDocument()
  })

  it('shows a retry-able error state when the first page fails to load', async () => {
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({ error: { code: 'internal_error', message: 'Boom.' } }, { status: 500 }),
      ),
    )
    renderWithProviders(<NotificationsPanel />)

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load notifications")
  })

  it('renders follow/like/reply rows with actor, verb, and unread indicator, and updates the unread count', async () => {
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [
            item({ id: 'n-follow', type: 'follow', tweet_id: null }),
            item({ id: 'n-like', type: 'like' }),
            item({ id: 'n-reply', type: 'reply', is_read: true }),
          ],
          page: { next_cursor: null },
          unread_count: 2,
        }),
      ),
    )
    renderWithProviders(<NotificationsPanel />)

    expect(await screen.findByText('2 unread notifications')).toBeInTheDocument()
    expect(screen.getByText(/Grace Hopper followed you/)).toBeInTheDocument()
    expect(screen.getByText(/Grace Hopper liked your tweet/)).toBeInTheDocument()
    expect(screen.getByText(/Grace Hopper replied to your tweet/)).toBeInTheDocument()

    const list = screen.getByRole('list', { name: 'Notifications' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
  })

  it('"Mark all read" marks every row read and zeroes the unread count', async () => {
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [item({ id: 'a' }), item({ id: 'b' })],
          page: { next_cursor: null },
          unread_count: 2,
        }),
      ),
      http.post('*/api/v1/notifications/read', () =>
        HttpResponse.json({ marked_read: 2, unread_count: 0 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<NotificationsPanel />)
    await screen.findByText('2 unread notifications')

    // Keyboard operability: tab to the button and activate with Enter/Space.
    const markAll = screen.getByRole('button', { name: 'Mark all read' })
    await user.tab()
    while (document.activeElement !== markAll) {
      await user.tab()
    }
    await user.keyboard('{Enter}')

    await waitFor(() => expect(screen.getByText('0 unread notifications')).toBeInTheDocument())
  })

  it('selecting rows via checkbox enables "Mark selected read", which marks only those rows read', async () => {
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [item({ id: 'a' }), item({ id: 'b' })],
          page: { next_cursor: null },
          unread_count: 2,
        }),
      ),
      http.post('*/api/v1/notifications/read', async ({ request }) => {
        const body = (await request.json()) as { notification_ids: string[] }
        return HttpResponse.json({ marked_read: body.notification_ids.length, unread_count: 1 })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<NotificationsPanel />)
    await screen.findByText('2 unread notifications')

    const markSelected = screen.getByRole('button', { name: 'Mark selected read' })
    expect(markSelected).toBeDisabled()

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])
    expect(markSelected).toBeEnabled()

    await user.click(markSelected)

    await waitFor(() => expect(screen.getByText('1 unread notification')).toBeInTheDocument())
  })

  it('shows "Load more" when a next page is available and fetches it on click', async () => {
    server.use(
      http.get('*/api/v1/notifications', ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('cursor') === 'page2') {
          return HttpResponse.json({
            data: [item({ id: 'page2-item' })],
            page: { next_cursor: null },
            unread_count: 3,
          })
        }
        return HttpResponse.json({
          data: [item({ id: 'page1-item' })],
          page: { next_cursor: 'page2' },
          unread_count: 3,
        })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<NotificationsPanel />)
    await screen.findByRole('button', { name: 'Load more' })

    const loadMore = screen.getByRole('button', { name: 'Load more' })
    await user.click(loadMore)

    await waitFor(() => expect(screen.getByText("You're all caught up.")).toBeInTheDocument())
    const list = screen.getByRole('list', { name: 'Notifications' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
  })

  it('has no obvious accessibility violations in its populated state', async () => {
    server.use(
      http.get('*/api/v1/notifications', () =>
        HttpResponse.json({
          data: [item({ id: 'a' }), item({ id: 'b', is_read: true })],
          page: { next_cursor: null },
          unread_count: 1,
        }),
      ),
    )
    const { container } = renderWithProviders(<NotificationsPanel />)
    await screen.findByText('1 unread notification')

    expect(await axe(container)).toHaveNoViolations()
  })
})
