import type { ReactNode } from 'react'

export interface EmptyStateProps {
  title: string
  description?: string
  /** Optional call-to-action, e.g. a Button. */
  action?: ReactNode
}

/** Friendly placeholder for lists/feeds with no content yet. */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-card border border-dashed border-border px-6 py-12 text-center">
      <p className="text-lg font-semibold text-foreground">{title}</p>
      {description ? (
        <p className="max-w-sm text-sm text-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}
