import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Menu } from 'lucide-react'
import { Logo } from '@/components/logo'
import { buttonVariants } from '@/components/ui/button'
import { Drawer } from '@/components/ui/drawer'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/lib/stores/session-store'
import { getOwnProfile } from '@/lib/api/profiles'
import { AccountMenu } from './account-menu'
import { NotificationBell } from './notification-bell'

export function Header() {
  const session = useSessionStore((state) => state.session)
  const [menuOpen, setMenuOpen] = useState(false)
  const signedIn = session?.stage === 'active'
  const { data: profile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, enabled: signedIn, retry: false })

  // Primary navigation (Discover, Status, Safety, Settings, sign out, create
  // post) lives in the floating BottomNav on every breakpoint. The header
  // keeps the secondary, account-scoped controls: notifications and the
  // profile dropdown, also on every breakpoint.
  if (signedIn) {
    return (
      <header className="sticky top-0 z-30 border-b border-ink-100 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/discover" aria-label="Flingra home">
            <Logo className="text-ink-900" />
          </Link>
          <div className="flex items-center gap-2.5">
            <NotificationBell />
            <AccountMenu name={profile?.displayName ?? session.maskedContact} photo={profile?.photos[0]} />
          </div>
        </div>
      </header>
    )
  }

  return (
    <header className="sticky top-0 z-30 border-b border-ink-100 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link to="/" aria-label="Flingra home">
          <Logo className="text-ink-900" />
        </Link>

        <div className="hidden items-center gap-3 md:flex">
          <Link to="/login" className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }))}>
            Sign in
          </Link>
          <Link to="/signup" className={cn(buttonVariants({ variant: 'accent', size: 'sm' }))}>
            Join
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
          className="flex size-11 cursor-pointer items-center justify-center rounded-full bg-white text-ink-700 shadow-soft transition-shadow hover:shadow-float md:hidden"
        >
          <Menu className="size-5" aria-hidden="true" />
        </button>
      </div>

      <Drawer open={menuOpen} onClose={() => setMenuOpen(false)} title="Menu">
        <nav className="flex flex-col gap-1" aria-label="Mobile">
          <Link to="/login" onClick={() => setMenuOpen(false)} className="rounded-xl px-3 py-3 text-base font-medium text-ink-800 hover:bg-ink-50">
            Sign in
          </Link>
          <Link to="/signup" onClick={() => setMenuOpen(false)} className="rounded-xl px-3 py-3 text-base font-semibold text-primary-600 hover:bg-primary-50">
            Join
          </Link>
          <Link to="/safety" onClick={() => setMenuOpen(false)} className="rounded-xl px-3 py-3 text-base font-medium text-ink-800 hover:bg-ink-50">
            Safety
          </Link>
        </nav>
      </Drawer>
    </header>
  )
}
