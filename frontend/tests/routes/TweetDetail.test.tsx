import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from '../../src/App'
import { server } from '../mocks/server'
import { testUser } from '../mocks/handlers'

/**
 * Tweet-detail screen integration tests (TSC-TWEET-002): renders a root
 * tweet with its replies and a reply composer, hides the reply composer
 * when the tweet is itself a reply (nested replies are impossible), and
 * fails safely (a rendered `ErrorState`, no crash) for a 404.
 */

function mockAuthenticatedSession() {
  server.use(
    http.post('*/api/v1/auth/refresh', () =>
      HttpResponse.json({ access_token: 'restored-token', token_type: 'bearer', expires_in: 900 }),
    ),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(testUser)),
  )
}

const ROOT_TWEET = {
  id: 'tweet-root',
  author: { id: testUser.id, username: testUser.username, name: testUser.name, avatar_key: null },
  content: 'A root tweet that can be replied to.',
  parent_tweet_id: null,
  like_count: 1,
  reply_count: 1,
  liked_by_viewer: false,
  media: [],
  links: [],
  created_at: '2026-02-01T00:00:00Z',
}

const REPLY_TWEET = {
  id: 'tweet-reply',
  author: { id: 'user-2', username: 'bob', name: 'Bob Builder', avatar_key: null },
  content: 'A reply to the root tweet.',
  parent_tweet_id: 'tweet-root',
  like_count: 0,
  reply_count: 0,
  liked_by_viewer: false,
  media: [],
  links: [],
  created_at: '2026-02-01T01:00:00Z',
}

describe('TweetDetail', () => {
  it('renders a root tweet, its reply composer, and its flat replies', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/tweets/tweet-root', () => HttpResponse.json(ROOT_TWEET)),
      http.get('*/api/v1/tweets/tweet-root/replies', () =>
        HttpResponse.json({ data: [REPLY_TWEET], page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/tweet/tweet-root')
    render(<App />)

    expect(await screen.findByText('A root tweet that can be replied to.')).toBeInTheDocument()
    expect(screen.getByLabelText('Post your reply')).toBeInTheDocument()
    expect(await screen.findByText('A reply to the root tweet.')).toBeInTheDocument()
  })

  it('does not render a reply composer when the tweet is itself a reply', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/tweets/tweet-reply', () => HttpResponse.json(REPLY_TWEET)),
      http.get('*/api/v1/tweets/tweet-reply/replies', () =>
        HttpResponse.json({ data: [], page: { next_cursor: null } }),
      ),
    )
    window.history.pushState({}, '', '/tweet/tweet-reply')
    render(<App />)

    expect(await screen.findByText('A reply to the root tweet.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Post your reply')).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Reply composer' })).not.toBeInTheDocument()
    expect(await screen.findByText('No replies yet')).toBeInTheDocument()
  })

  it('renders a not-found error state for an unknown tweet id, without crashing', async () => {
    mockAuthenticatedSession()
    server.use(
      http.get('*/api/v1/tweets/missing', () =>
        HttpResponse.json(
          { error: { code: 'not_found', message: 'Tweet not found.' } },
          { status: 404 },
        ),
      ),
    )
    window.history.pushState({}, '', '/tweet/missing')
    render(<App />)

    const alert = await screen.findByRole('alert')
    await waitFor(() => expect(alert).toHaveTextContent('Tweet not found'))
  })
})
