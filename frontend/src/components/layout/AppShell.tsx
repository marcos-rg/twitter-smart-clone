import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

export interface AppShellProps {
  children: ReactNode
}

const navItems = [
  { to: '/', label: 'Home', icon: '🏠' },
  { to: '/lab', label: 'Design Lab', icon: '🧪' },
]

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
              <span className="hidden lg:inline">{item.label}</span>
              <span className="sr-only lg:hidden">{item.label}</span>
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
            aria-label={item.label}
            className={({ isActive }) =>
              [
                'rounded-full p-3 text-xl transition-colors duration-150 motion-reduce:transition-none',
                isActive ? 'bg-surface-hover' : 'hover:bg-surface-hover',
              ].join(' ')
            }
          >
            <span aria-hidden="true">{item.icon}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
