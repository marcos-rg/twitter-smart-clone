import { Button } from './Button'
import { AlertCircleIcon } from './icons'

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
      className="flex flex-col items-center gap-3 rounded-card border border-danger/30 bg-danger/5 px-6 py-14 text-center"
    >
      <span className="flex size-12 items-center justify-center rounded-full bg-danger/10 text-danger">
        <AlertCircleIcon className="size-6" />
      </span>
      <p className="text-lg font-semibold text-foreground">{title}</p>
      <p className="max-w-sm text-sm text-muted">{description}</p>
      {onRetry ? (
        <div className="mt-1">
          <Button variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  )
}
