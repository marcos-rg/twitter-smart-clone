import type { ReactNode } from 'react'
import { InboxIcon } from './icons'

export interface EmptyStateProps {
  title: string
  description?: string
  /** Optional call-to-action, e.g. a Button. */
  action?: ReactNode
}

/** Friendly placeholder for lists/feeds with no content yet. */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-card border border-dashed border-border-strong bg-surface/40 px-6 py-14 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-surface-hover text-muted">
        <InboxIcon className="size-6" />
      </span>
      <p className="text-lg font-semibold text-foreground">{title}</p>
      {description ? <p className="max-w-sm text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  )
}
