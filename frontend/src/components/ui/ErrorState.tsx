import { Button } from './Button'

export interface ErrorStateProps {
  title?: string
  description?: string
  /** When provided, renders a retry button that calls this handler. */
  onRetry?: () => void
}

/** Error placeholder with an optional retry action. Announced assertively. */
export function ErrorState({
  title = 'Something went wrong',
  description = 'We could not load this content. Please try again.',
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-2 rounded-card border border-danger/50 px-6 py-12 text-center"
    >
      <p className="text-lg font-semibold text-foreground">{title}</p>
      <p className="max-w-sm text-sm text-muted">{description}</p>
      {onRetry ? (
        <div className="mt-2">
          <Button variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  )
}
