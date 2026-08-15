import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { ToastContext, type ToastVariant } from './toast-context'
import { CheckCircleIcon, InfoIcon, XIcon, AlertCircleIcon } from './icons'

interface ToastItem {
  id: number
  message: string
  variant: ToastVariant
}

const variantClasses: Record<ToastVariant, string> = {
  info: 'border-border-strong text-foreground',
  success: 'border-success/40 text-foreground',
  error: 'border-danger/40 text-foreground',
}

const variantIconClasses: Record<ToastVariant, string> = {
  info: 'text-brand',
  success: 'text-success',
  error: 'text-danger',
}

function ToastIcon({ variant }: { variant: ToastVariant }) {
  const className = `size-5 shrink-0 ${variantIconClasses[variant]}`
  if (variant === 'success') return <CheckCircleIcon className={className} />
  if (variant === 'error') return <AlertCircleIcon className={className} />
  return <InfoIcon className={className} />
}

const AUTO_DISMISS_MS = 5000
let nextId = 1

/**
 * Toast notification system. Wrap the app in ToastProvider and call
 * `useToast().toast('message', 'success')` from any component. Toasts are
 * announced politely (assertively for errors) and auto-dismiss.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback((message: string, variant: ToastVariant = 'info') => {
    const id = nextId++
    setToasts((current) => [...current, { id, message, variant }])
    setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id))
    }, AUTO_DISMISS_MS)
  }, [])

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.variant === 'error' ? 'alert' : 'status'}
            className={`pointer-events-auto flex w-full max-w-sm items-center gap-3 rounded-control border bg-surface-raised px-4 py-3 text-sm shadow-panel motion-safe:animate-[fade-in_200ms_ease-out] ${variantClasses[t.variant]}`}
          >
            <ToastIcon variant={t.variant} />
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
              className="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted transition-colors duration-150 hover:bg-surface-hover hover:text-foreground motion-reduce:transition-none"
            >
              <XIcon className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
