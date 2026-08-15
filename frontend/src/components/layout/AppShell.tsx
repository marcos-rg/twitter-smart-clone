import type { ReactElement, ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../stores/auth-store'
import { useNotificationsStore } from '../../stores/notifications-store'
import { BellIcon, HomeIcon, Logomark, SearchIcon, UserIcon, type IconProps } from '../ui/icons'

export interface AppShellProps {
  children: ReactNode
}

interface NavItem {
  to: string
  label: string
  Icon: (props: IconProps) => ReactElement
  badge?: number
}

const baseNavItems: NavItem[] = [
  { to: '/', label: 'Home', Icon: HomeIcon },
  { to: '/search', label: 'Search', Icon: SearchIcon },
]

/** Unread-count pill on the Notifications nav item (TSC-NOTIF-002).
 * Capped at "99+" so a large count never breaks the nav's layout. */
function UnreadBadge({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span
      aria-hidden="true"
      className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1.5 text-xs font-semibold text-white shadow-glow lg:ml-0"
    >
      {count > 99 ? '99+' : count}
    </span>
  )
}

/** Brand wordmark: gradient sparkle mark + text (text hidden below `lg`, same
 * pattern as the nav item labels below). */
function Wordmark() {
  return (
    <span className="flex items-center gap-2.5 px-2 pb-4">
      <Logomark className="size-8" />
      <span className="hidden text-lg font-extrabold tracking-tight text-foreground lg:inline">
        Twitter Smart Clone
      </span>
    </span>
  )
}

/**
 * Responsive application shell.
 *
 * - Mobile (<640px): top header bar + bottom navigation.
 * - Tablet (640–1024px): compact icon-only left sidebar.
 * - Desktop (>1024px): full sidebar with labels.
 *
 * Includes a skip link so keyboard users can jump straight to the content.
 */
export function AppShell({ children }: AppShellProps) {
  // "Profile" needs the signed-in user's own username to link to
  // (TSC-USER-002), so it's only added to the nav once a session is
  // restored; unauthenticated visitors (e.g. on /login) don't see it.
  const username = useAuthStore((state) => state.user?.username)
  const unreadCount = useNotificationsStore((state) => state.unreadCount)
  const navItems = [
    ...baseNavItems,
    ...(username
      ? [
          { to: '/notifications', label: 'Notifications', Icon: BellIcon, badge: unreadCount },
          { to: `/profile/${username}`, label: 'Profile', Icon: UserIcon },
        ]
      : []),
  ]

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-brand focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-40 flex items-center gap-2.5 border-b border-border bg-canvas/80 px-4 py-3 backdrop-blur-md sm:hidden">
        <Logomark className="size-7" />
        <span className="text-lg font-extrabold tracking-tight">Twitter Smart Clone</span>
      </header>

      <div className="mx-auto flex max-w-6xl">
        <nav
          aria-label="Primary"
          className="sticky top-0 hidden h-screen w-16 shrink-0 flex-col gap-1 border-r border-border px-2 py-4 sm:flex lg:w-64 lg:px-3"
        >
          <Wordmark />
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              // An explicit `aria-label` when there's an unread count so the
              // announcement survives every breakpoint — the visible label
              // text is `hidden` below `lg`, and the icon-only breakpoint's
              // `sr-only` fallback would otherwise itself go `lg:hidden` at
              // the *wide* end, silently dropping the unread count from a
              // desktop screen reader user's accessible name.
              aria-label={item.badge ? `${item.label}, ${item.badge} unread` : undefined}
              className={({ isActive }) =>
                [
                  'group flex items-center gap-4 rounded-full px-3 py-2.5 text-base transition-colors duration-150 motion-reduce:transition-none lg:px-4',
                  isActive
                    ? 'bg-brand-soft font-bold text-foreground'
                    : 'text-foreground/75 hover:bg-surface-hover hover:text-foreground',
                ].join(' ')
              }
            >
              {({ isActive }) => (
                <>
                  <item.Icon
                    className={`size-6 shrink-0 transition-colors duration-150 motion-reduce:transition-none ${isActive ? 'text-brand' : ''}`}
                  />
                  <span className="hidden lg:inline" aria-hidden={item.badge ? true : undefined}>
                    {item.label}
                  </span>
                  <span className="sr-only lg:hidden" aria-hidden={item.badge ? true : undefined}>
                    {item.label}
                  </span>
                  {item.badge ? <UnreadBadge count={item.badge} /> : null}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <main id="main-content" className="min-w-0 flex-1 border-r border-border pb-20 sm:pb-0">
          {children}
        </main>
      </div>

      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-border bg-canvas/90 py-1.5 backdrop-blur-md sm:hidden"
      >
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            aria-label={item.badge ? `${item.label}, ${item.badge} unread` : item.label}
            className={({ isActive }) =>
              [
                'relative flex items-center justify-center rounded-full p-3 transition-colors duration-150 motion-reduce:transition-none',
                isActive ? 'text-brand' : 'text-foreground/75 hover:bg-surface-hover',
              ].join(' ')
            }
          >
            <item.Icon className="size-6" />
            {item.badge ? (
              <span
                aria-hidden="true"
                className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-semibold text-white"
              >
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            ) : null}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
