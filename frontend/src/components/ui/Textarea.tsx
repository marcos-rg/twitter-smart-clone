import { forwardRef, useId, type TextareaHTMLAttributes } from 'react'

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string
  /** Validation message. When set, the textarea is marked aria-invalid. */
  error?: string
  /** Optional helper text shown below the textarea when there is no error. */
  hint?: string
}

/**
 * Labelled multi-line input with the same error/hint wiring as Input.
 */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ label, error, hint, id, className = '', rows = 3, ...rest }, ref) {
    const autoId = useId()
    const textareaId = id ?? autoId
    const messageId = `${textareaId}-message`
    const hasMessage = Boolean(error || hint)

    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={textareaId} className="text-sm font-semibold text-foreground">
          {label}
        </label>
        <textarea
          ref={ref}
          id={textareaId}
          rows={rows}
          aria-invalid={error ? true : undefined}
          aria-describedby={hasMessage ? messageId : undefined}
          className={[
            'resize-y rounded-control border bg-surface px-3 py-2 text-foreground transition-colors duration-150 motion-reduce:transition-none',
            error
              ? 'border-danger'
              : 'border-border hover:border-muted focus:border-brand',
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
  },
)
