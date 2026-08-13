export interface SkeletonProps {
  /** Tailwind classes controlling shape/size, e.g. "h-4 w-32 rounded-full". */
  className?: string
  /** Accessible label announced while content loads. */
  label?: string
}

/**
 * Loading placeholder block. Decorative by default (aria-hidden) since the
 * surrounding container should own the loading announcement via `label` or an
 * aria-busy region. Pulse animation is disabled under prefers-reduced-motion
 * by the global reduced-motion rule in index.css.
 */
export function Skeleton({ className = '', label }: SkeletonProps) {
  return (
    <div
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={`animate-pulse rounded bg-surface-hover ${className}`}
    >
      {label ? <span className="sr-only">{label}</span> : null}
    </div>
  )
}
