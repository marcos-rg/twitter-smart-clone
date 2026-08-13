import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it, vi } from 'vitest'
import { Avatar } from '../../src/components/ui/Avatar'
import { EmptyState } from '../../src/components/ui/EmptyState'
import { ErrorState } from '../../src/components/ui/ErrorState'
import { Skeleton } from '../../src/components/ui/Skeleton'
import { TweetCard, TweetCardSkeleton } from '../../src/components/tweet/TweetCard'

describe('Avatar', () => {
  it('renders initials with an accessible name when no image is given', () => {
    render(<Avatar name="Ada Lovelace" />)
    expect(screen.getByRole('img', { name: 'Ada Lovelace' })).toHaveTextContent('AL')
  })

  it('renders a single initial for one-word names', () => {
    render(<Avatar name="Cher" />)
    expect(screen.getByRole('img', { name: 'Cher' })).toHaveTextContent('C')
  })

  it('falls back to initials when the image fails to load', () => {
    render(<Avatar name="Grace Hopper" src="/broken.png" />)
    fireEvent.error(screen.getByAltText('Grace Hopper'))
    expect(screen.getByRole('img', { name: 'Grace Hopper' })).toHaveTextContent('GH')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Avatar name="Ada Lovelace" />
        <Avatar name="With Image" src="/avatar.png" size="lg" />
      </>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('Skeleton', () => {
  it('is decorative by default', () => {
    const { container } = render(<Skeleton className="h-4 w-4" />)
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('announces itself when given a label', () => {
    render(<Skeleton className="h-4 w-4" label="Loading preview" />)
    expect(screen.getByRole('status', { name: 'Loading preview' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<Skeleton className="h-24 w-full" label="Loading" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('TweetCard', () => {
  const props = {
    authorName: 'Ada Lovelace',
    authorHandle: 'ada',
    timestamp: '2026-08-13T14:00:00Z',
    content: 'Hello world',
    replyCount: 2,
    repostCount: 3,
    likeCount: 4,
  }

  it('renders author, content, and accessible action counts', () => {
    render(<TweetCard {...props} />)
    expect(screen.getByRole('article', { name: 'Tweet by Ada Lovelace' })).toBeInTheDocument()
    expect(screen.getByText('@ada')).toBeInTheDocument()
    expect(screen.getByText('Hello world')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reply, 2 replies' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Repost, 3 reposts' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Like, 4 likes' })).toBeInTheDocument()
  })

  it('renders an invalid timestamp as-is', () => {
    render(<TweetCard {...props} timestamp="not-a-date" />)
    expect(screen.getByText('not-a-date')).toBeInTheDocument()
  })

  it('has no accessibility violations, including long content', async () => {
    const { container } = render(
      <>
        <TweetCard {...props} />
        <TweetCard {...props} content={`${'verylongword'.repeat(100)}`} />
      </>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders a labelled loading skeleton', () => {
    render(<TweetCardSkeleton />)
    expect(screen.getByRole('status', { name: 'Loading tweet' })).toBeInTheDocument()
  })
})

describe('EmptyState', () => {
  it('renders title, description, and action', () => {
    render(
      <EmptyState
        title="No tweets yet"
        description="Follow people to fill your feed."
        action={<button type="button">Find people</button>}
      />,
    )
    expect(screen.getByText('No tweets yet')).toBeInTheDocument()
    expect(screen.getByText('Follow people to fill your feed.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Find people' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<EmptyState title="Nothing here" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('ErrorState', () => {
  it('announces itself assertively and calls onRetry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<ErrorState onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('omits the retry button when no handler is provided', () => {
    render(<ErrorState title="Custom title" description="Custom description" />)
    expect(screen.getByText('Custom title')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ErrorState onRetry={() => {}} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
