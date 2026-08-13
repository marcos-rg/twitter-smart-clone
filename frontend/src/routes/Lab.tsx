import { useState, type ReactNode } from 'react'
import {
  Avatar,
  Button,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Skeleton,
  Tabs,
  Textarea,
  useToast,
} from '../components/ui'
import { TweetCard, TweetCardSkeleton } from '../components/tweet/TweetCard'

const LONG_CONTENT =
  'This is an intentionally long tweet to verify that long content wraps ' +
  'correctly and never causes horizontal overflow. '.repeat(6) +
  'https://example.com/a-very-long-url/that/keeps/going/and/going/without/spaces/to/test/word-breaking'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`lab-${title.replace(/\s+/g, '-').toLowerCase()}`} className="border-b border-border px-4 py-6">
      <h2
        id={`lab-${title.replace(/\s+/g, '-').toLowerCase()}`}
        className="mb-4"
      >
        {title}
      </h2>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-muted">{label}</p>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  )
}

/**
 * Component interaction lab (TSC-UX-001). Development route that renders
 * every design-system component in its representative states — default,
 * loading, disabled, error, empty, and long-content — for visual review and
 * responsive/a11y checks. Not linked into production feature flows.
 */
export function Lab() {
  const [modalOpen, setModalOpen] = useState(false)
  const { toast } = useToast()

  return (
    <div>
      <header className="border-b border-border px-4 py-6">
        <h1>Design Lab</h1>
        <p className="mt-1 text-sm text-muted">
          Isolated showcase of the design system components and their states.
        </p>
      </header>

      <Section title="Button">
        <Row label="Variants">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
        </Row>
        <Row label="Sizes">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </Row>
        <Row label="States">
          <Button loading>Loading</Button>
          <Button disabled>Disabled</Button>
        </Row>
      </Section>

      <Section title="Input">
        <Input label="Username" placeholder="e.g. ada_lovelace" />
        <Input label="Email" hint="We will never share your email." placeholder="you@example.com" />
        <Input label="Password" type="password" error="Password must be at least 8 characters." defaultValue="short" />
        <Input label="Disabled field" disabled defaultValue="Cannot edit" />
      </Section>

      <Section title="Textarea">
        <Textarea label="Bio" placeholder="Tell the world about yourself" />
        <Textarea label="Bio (error)" error="Bio cannot exceed 160 characters." defaultValue={'x'.repeat(200)} />
      </Section>

      <Section title="Avatar">
        <Row label="Sizes & fallbacks">
          <Avatar name="Ada Lovelace" size="sm" />
          <Avatar name="Grace Hopper" size="md" />
          <Avatar name="Alan Turing" size="lg" />
          <Avatar name="Broken Image" src="/does-not-exist.png" />
        </Row>
      </Section>

      <Section title="Modal">
        <Button onClick={() => setModalOpen(true)}>Open modal</Button>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Example modal"
        >
          <p className="text-sm text-muted">
            Focus is trapped here. Press Escape or click the backdrop to close.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => setModalOpen(false)}>Confirm</Button>
          </div>
        </Modal>
      </Section>

      <Section title="Toast">
        <Row label="Trigger notifications">
          <Button variant="outline" onClick={() => toast('Tweet posted.')}>
            Info
          </Button>
          <Button variant="outline" onClick={() => toast('Profile saved.', 'success')}>
            Success
          </Button>
          <Button variant="outline" onClick={() => toast('Could not post tweet.', 'error')}>
            Error
          </Button>
        </Row>
      </Section>

      <Section title="Skeleton">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-24 w-full rounded-card" label="Loading preview" />
      </Section>

      <Section title="Tabs">
        <Tabs
          aria-label="Example feed tabs"
          tabs={[
            { id: 'for-you', label: 'For you', content: <p className="text-sm text-muted">Algorithmic feed content.</p> },
            { id: 'following', label: 'Following', content: <p className="text-sm text-muted">Chronological feed content.</p> },
            { id: 'disabled', label: 'Disabled', content: null, disabled: true },
          ]}
        />
      </Section>

      <Section title="Tweet card">
        <div className="rounded-card border border-border">
          <TweetCard
            authorName="Ada Lovelace"
            authorHandle="ada"
            timestamp="2026-08-13T14:00:00Z"
            content="Just shipped the design system. Tokens, focus styles, and reduced-motion support all in."
            replyCount={12}
            repostCount={34}
            likeCount={156}
          />
          <TweetCard
            authorName="Long Content Author With A Very Long Display Name"
            authorHandle="averylonghandlethatestswrapping"
            timestamp="2026-08-13T13:00:00Z"
            content={LONG_CONTENT}
            replyCount={0}
            repostCount={0}
            likeCount={0}
          />
          <TweetCardSkeleton />
        </div>
      </Section>

      <Section title="Empty & error states">
        <EmptyState
          title="No tweets yet"
          description="When people you follow post, their tweets will show up here."
          action={<Button size="sm">Find people to follow</Button>}
        />
        <ErrorState onRetry={() => toast('Retrying…')} />
      </Section>
    </div>
  )
}
