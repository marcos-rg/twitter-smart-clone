import { forwardRef, useId, type InputHTMLAttributes } from 'react'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  /** Validation message. When set, the input is marked aria-invalid. */
  error?: string
  /** Optional helper text shown below the input when there is no error. */
  hint?: string
  /** Visually hides the label (still in the accessibility tree via sr-only)
   * for compact, placeholder-led layouts like the tweet composer. */
  hideLabel?: boolean
}

/**
 * Labelled text input with error and hint support. The label is always
 * rendered (visually, unless `hideLabel`) and associated via htmlFor; errors
 * are wired through aria-invalid + aria-describedby so screen readers
 * announce them.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, hideLabel, id, className = '', ...rest },
  ref,
) {
  const autoId = useId()
  const inputId = id ?? autoId
  const messageId = `${inputId}-message`
  const hasMessage = Boolean(error || hint)

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={inputId}
        className={hideLabel ? 'sr-only' : 'text-sm font-semibold text-foreground'}
      >
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={hasMessage ? messageId : undefined}
        className={[
          'h-11 rounded-control border bg-surface px-3.5 text-foreground shadow-sm transition-colors duration-150 motion-reduce:transition-none',
          error ? 'border-danger' : 'border-border hover:border-border-strong focus:border-brand',
          className,
        ].join(' ')}
        {...rest}
      />
      {hasMessage ? (
        <p
          id={messageId}
          role={error ? 'alert' : undefined}
          className={`text-xs ${error ? 'text-danger' : 'text-muted'}`}
        >
          {error ?? hint}
        </p>
      ) : null}
    </div>
  )
})
