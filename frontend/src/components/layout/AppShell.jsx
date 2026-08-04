import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import {

  GraduationCap,
  History,
  LayoutDashboard,
  Menu,
  Upload,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/app/upload', icon: Upload, label: 'New package' },
  { to: '/app/library', icon: History, label: 'Library' },
]

/** Wordmark. Always routes to the landing page, from anywhere in the app. */
function Wordmark({ className, iconSize = 18 }) {
  return (
    <Link
      to="/"
      aria-label="Gyantra — go to home page"
      className={cn(
        'flex items-center gap-2.5 rounded-lg transition-opacity hover:opacity-80',
        className,
      )}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-solid text-white">
        <GraduationCap size={iconSize} aria-hidden="true" />
      </span>
      <span className="font-display text-[17px] font-semibold tracking-tight text-fg-strong">
        Gyantra
      </span>
    </Link>
  )
}

function NavItem({ to, icon: Icon, label, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-lg px-3 py-2.5',
          'text-[14px] font-medium transition-colors',
          isActive
            ? 'bg-accent-soft text-accent-fg'
            : 'text-fg-muted hover:bg-app-subtle hover:text-fg',
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Active marker: not colour-only, so it survives high-contrast modes */}
          <span
            className={cn(
              'absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full transition-all',
              isActive ? 'bg-[rgb(var(--accent))] opacity-100' : 'opacity-0',
            )}
            aria-hidden="true"
          />
          <Icon size={18} aria-hidden="true" />
          {label}
        </>
      )}
    </NavLink>
  )
}

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  // Lock body scroll while the drawer covers the screen.
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [drawerOpen])

  return (
    <div className="theme-light flex min-h-screen bg-app">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:shadow-lg"
      >
        Skip to content
      </a>

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col',
          'border-r border-default bg-surface',
          'transition-transform duration-200 ease-out',
          drawerOpen ? 'translate-x-0' : '-translate-x-full',
          'sm:static sm:translate-x-0',
        )}
      >
        <div className="flex h-16 items-center border-b border-default px-5">
          <Wordmark />
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-5" aria-label="Main">
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>

        <div className="border-t border-default px-5 py-4">
          <p className="text-[12px] leading-relaxed text-fg-subtle">
            Turn any chapter into a grounded, classroom-ready teaching package.
          </p>
        </div>
      </aside>

      {drawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm sm:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-default bg-surface/85 px-4 backdrop-blur-md sm:px-6">
          <button
            onClick={() => setDrawerOpen((v) => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-app-subtle hover:text-fg sm:hidden"
            aria-label={drawerOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={drawerOpen}
          >
            {drawerOpen ? <X size={19} /> : <Menu size={19} />}
          </button>

          {/* Mobile wordmark — the sidebar one is off-screen */}
          <Wordmark className="sm:hidden" iconSize={17} />

          <div className="flex-1" />

        </header>

        <main id="main" className="flex-1">
          <div className="container-content py-7 sm:py-9">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

/** Marketing layout — dark theme, no sidebar. */
export function MarketingShell() {
  return (
    <div className="theme-dark flex min-h-screen flex-col bg-app">
      <header className="sticky top-0 z-20 border-b border-default bg-app/80 backdrop-blur-md">
        <div className="container-content flex h-16 items-center">
          <Wordmark iconSize={19} />
          <div className="flex-1" />
          <nav className="flex items-center gap-1" aria-label="Primary">
            <NavLink
              to="/app"
              className="rounded-lg px-4 py-2 text-[14px] font-medium text-fg-muted transition-colors hover:bg-app-subtle hover:text-fg"
            >
              Workspace
            </NavLink>
            <NavLink
              to="/app/upload"
              className="rounded-lg bg-accent-solid px-4 py-2 text-[14px] font-medium text-white transition-all hover:brightness-110"
            >
              Try it
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-default py-8">
        <div className="container-content text-center text-[13px] text-fg-subtle">
          Gyantra — From Chapter to Classroom
        </div>
      </footer>
    </div>
  )
}
