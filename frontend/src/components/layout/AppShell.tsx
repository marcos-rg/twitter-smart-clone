import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../stores/auth-store'
import { useNotificationsStore } from '../../stores/notifications-store'

export interface AppShellProps {
  children: ReactNode
}

interface NavItem {
  to: string
  label: string
  icon: string
  badge?: number
}

const baseNavItems: NavItem[] = [
  { to: '/', label: 'Home', icon: '🏠' },
  { to: '/search', label: 'Search', icon: '🔍' },
]

const labNavItem: NavItem = { to: '/lab', label: 'Design Lab', icon: '🧪' }

/** Unread-count pill on the Notifications nav item (TSC-NOTIF-002).
 * Capped at "99+" so a large count never breaks the nav's layout. */
function UnreadBadge({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span
      aria-hidden="true"
      className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1 text-xs font-semibold text-white lg:ml-0"
    >
      {count > 99 ? '99+' : count}
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
          { to: '/notifications', label: 'Notifications', icon: '🔔', badge: unreadCount },
          { to: `/profile/${username}`, label: 'Profile', icon: '👤' },
        ]
      : []),
    labNavItem,
  ]

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-brand focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-40 border-b border-border bg-canvas/80 px-4 py-3 backdrop-blur sm:hidden">
        <span className="text-lg font-bold">Twitter Smart Clone</span>
      </header>

      <div className="mx-auto flex max-w-6xl">
        <nav
          aria-label="Primary"
          className="sticky top-0 hidden h-screen w-16 shrink-0 flex-col gap-2 border-r border-border px-2 py-4 sm:flex lg:w-64 lg:px-4"
        >
          <span className="hidden px-2 pb-4 text-lg font-bold lg:block">Twitter Smart Clone</span>
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
                  'flex items-center gap-3 rounded-full px-3 py-2 text-base transition-colors duration-150 motion-reduce:transition-none',
                  isActive
                    ? 'font-bold text-foreground'
                    : 'text-foreground/80 hover:bg-surface-hover',
                ].join(' ')
              }
            >
              <span aria-hidden="true">{item.icon}</span>
              <span className="hidden lg:inline" aria-hidden={item.badge ? true : undefined}>
                {item.label}
              </span>
              <span className="sr-only lg:hidden" aria-hidden={item.badge ? true : undefined}>
                {item.label}
              </span>
              {item.badge ? <UnreadBadge count={item.badge} /> : null}
            </NavLink>
          ))}
        </nav>

        <main id="main-content" className="min-w-0 flex-1 pb-20 sm:pb-0">
          {children}
        </main>
      </div>

      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-border bg-canvas py-2 sm:hidden"
      >
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            aria-label={item.badge ? `${item.label}, ${item.badge} unread` : item.label}
            className={({ isActive }) =>
              [
                'relative rounded-full p-3 text-xl transition-colors duration-150 motion-reduce:transition-none',
                isActive ? 'bg-surface-hover' : 'hover:bg-surface-hover',
              ].join(' ')
            }
          >
            <span aria-hidden="true">{item.icon}</span>
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
