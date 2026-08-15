import type { SVGProps } from 'react'

export interface IconProps extends SVGProps<SVGSVGElement> {
  className?: string
}

/**
 * Small stroke-icon set (Feather-style: 24x24, round caps/joins) used
 * throughout the app in place of emoji glyphs. Every icon is `aria-hidden`
 * by default — the accessible name always comes from surrounding text or the
 * interactive element's own `aria-label`, never from the icon itself.
 */
function baseProps(props: IconProps): IconProps {
  const { className = '', ...rest } = props
  return {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
    className: `size-5 ${className}`,
    ...rest,
  }
}

export function HomeIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1v-9" />
    </svg>
  )
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  )
}

export function BellIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M6 8a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
      <path d="M9.5 20a2.5 2.5 0 0 0 5 0" />
    </svg>
  )
}

export function UserIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c1.5-4 5-6 8-6s6.5 2 8 6" />
    </svg>
  )
}

export function FlaskIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M9 3h6" />
      <path d="M10 3v6.2L4.7 18a2 2 0 0 0 1.7 3h11.2a2 2 0 0 0 1.7-3L14 9.2V3" />
      <path d="M7.5 15h9" />
    </svg>
  )
}

export function MessageCircleIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 8.5 8.5 0 0 1-4-1L3 20l1.1-4A8.4 8.4 0 0 1 3.5 11.5 8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z" />
    </svg>
  )
}

export function HeartIcon({ filled = false, ...props }: IconProps & { filled?: boolean }) {
  const p = baseProps(props)
  return (
    <svg {...p} fill={filled ? 'currentColor' : 'none'}>
      <path d="M12 20.5s-7-4.35-9.5-8.8C.7 8.4 2.1 5 5.6 4.2 8 3.6 10 4.6 12 7c2-2.4 4-3.4 6.4-2.8 3.5.8 4.9 4.2 3.1 7.5-2.5 4.45-9.5 8.8-9.5 8.8Z" />
    </svg>
  )
}

export function ImagePlusIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <circle cx="9" cy="10" r="1.75" />
      <path d="m4.5 18 5-5 4 4 3-3 4.5 4" />
    </svg>
  )
}

export function XIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </svg>
  )
}

export function LogOutIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M9 19H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h3" />
      <path d="m16 17 5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  )
}

export function ChevronLeftIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="m15 6-6 6 6 6" />
    </svg>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  )
}

export function AlertCircleIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.75v5.5" />
      <path d="M12 16.25h.01" />
    </svg>
  )
}

export function InboxIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4.5 12h3.7l1.6 2.4h4.4l1.6-2.4h3.7" />
      <path d="m5.3 12-1.1-5.8A2 2 0 0 1 6.2 4h11.6a2 2 0 0 1 2 2.2L18.7 12" />
      <path d="M5.3 12v6a2 2 0 0 0 2 2h9.4a2 2 0 0 0 2-2v-6" />
    </svg>
  )
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.3 12.3 2.5 2.5 5-5.2" />
    </svg>
  )
}

export function InfoIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.75h.01" />
      <path d="M11 11.5h1v5h1" />
    </svg>
  )
}

export function RefreshIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 12a8 8 0 0 1 13.66-5.66L20 8.5" />
      <path d="M20 4v4.5h-4.5" />
      <path d="M20 12a8 8 0 0 1-13.66 5.66L4 15.5" />
      <path d="M4 20v-4.5h4.5" />
    </svg>
  )
}

/** Sparkle brand glyph, used on its own or inside `Logomark`. */
export function SparkleIcon(props: IconProps) {
  const p = baseProps(props)
  return (
    <svg {...p} fill="currentColor" stroke="none">
      <path d="M12 2 14.2 9.8 22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2Z" />
    </svg>
  )
}

/** Rounded gradient app icon (sidebar wordmark, auth screens, favicon-style
 * mark). Purely decorative — always paired with a visible/sr-only wordmark. */
export function Logomark({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-accent text-white shadow-glow ${className}`}
    >
      <SparkleIcon className="size-[55%]" />
    </span>
  )
}
