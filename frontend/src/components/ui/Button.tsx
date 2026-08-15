import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Renders a spinner, sets aria-busy, and blocks interaction. */
  loading?: boolean
  children: ReactNode
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-brand text-white shadow-[0_1px_0_0_rgb(255_255_255/0.15)_inset,0_4px_14px_-4px_rgb(29_155_240/0.55)] hover:bg-brand-hover disabled:hover:bg-brand',
  secondary: 'bg-foreground text-canvas hover:bg-foreground/90 disabled:hover:bg-foreground',
  outline:
    'border border-border-strong bg-transparent text-foreground hover:border-border-strong hover:bg-surface-hover disabled:hover:bg-transparent',
  ghost: 'bg-transparent text-brand hover:bg-brand-soft disabled:hover:bg-transparent',
  danger:
    'bg-danger text-white shadow-[0_1px_0_0_rgb(255_255_255/0.15)_inset,0_4px_14px_-4px_rgb(244_33_46/0.55)] hover:bg-danger-hover disabled:hover:bg-danger',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
}

function Spinner() {
  return (
    <svg
      className="size-4 animate-spin motion-reduce:animate-none"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
    </svg>
  )
}

/**
 * Accessible button with variants, sizes, and a built-in loading state.
 * Loading buttons are disabled and announce `aria-busy` to screen readers.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    disabled,
    className = '',
    children,
    type = 'button',
    ...rest
  },
  ref,
) {
  const isDisabled = disabled || loading
  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={[
        'inline-flex cursor-pointer items-center justify-center gap-2 rounded-full font-semibold transition-[background-color,box-shadow,transform] duration-150 motion-reduce:transition-none',
        'active:scale-[0.97] motion-reduce:active:scale-100',
        'disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100',
        variantClasses[variant],
        sizeClasses[size],
        className,
      ].join(' ')}
      {...rest}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  )
})
