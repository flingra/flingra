import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { Circle, Compass, LogOut, Plus, Radio, Settings, ShieldCheck, Wallet } from 'lucide-react'
import { CreatePostDrawer } from '@/features/profile/components/create-post-drawer'
import { GoLiveDrawer } from '@/features/livestream/components/go-live-drawer'
import { signOut } from '@/lib/api/auth'
import { useSessionStore } from '@/lib/stores/session-store'

const NAV_ITEMS = [
  { to: '/discover', icon: Compass, label: 'Discover' },
  { to: '/status', icon: Circle, label: 'Status' },
  { to: '/wallet', icon: Wallet, label: 'Wallet' },
  { to: '/safety', icon: ShieldCheck, label: 'Safety' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function BottomNav() {
  const [createOpen, setCreateOpen] = useState(false)
  const [goLiveOpen, setGoLiveOpen] = useState(false)
  const navigate = useNavigate()
  const setSession = useSessionStore((state) => state.setSession)

  async function handleSignOut() {
    await signOut()
    setSession(null)
    navigate('/login')
  }

  return (
    <>
      <div className="fixed inset-x-0 bottom-4 z-30 flex items-center justify-center gap-3 px-4">
        <nav aria-label="Primary" className="flex items-center gap-1 rounded-full bg-ink-900 px-3 py-2.5 shadow-float">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              aria-label={label}
              className={({ isActive }) =>
                `flex size-11 items-center justify-center rounded-full transition-colors ${
                  isActive ? 'bg-white text-ink-900' : 'text-white/70 hover:text-white'
                }`
              }
            >
              <Icon className="size-5" aria-hidden="true" />
            </NavLink>
          ))}
          <button
            type="button"
            onClick={() => setGoLiveOpen(true)}
            aria-label="Go live"
            className="flex size-11 cursor-pointer items-center justify-center rounded-full text-white/70 transition-colors hover:text-danger"
          >
            <Radio className="size-5" aria-hidden="true" />
          </button>
          <div className="mx-1 h-6 w-px bg-white/15" aria-hidden="true" />
          <button
            type="button"
            onClick={handleSignOut}
            aria-label="Sign out"
            className="flex size-11 cursor-pointer items-center justify-center rounded-full text-white/70 transition-colors hover:text-danger"
          >
            <LogOut className="size-5" aria-hidden="true" />
          </button>
        </nav>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          aria-label="Create post"
          className="flex size-14 shrink-0 cursor-pointer items-center justify-center rounded-full bg-primary-500 text-white shadow-float transition-colors hover:bg-primary-600"
        >
          <Plus className="size-6" aria-hidden="true" />
        </button>
      </div>

      <CreatePostDrawer open={createOpen} onClose={() => setCreateOpen(false)} />
      <GoLiveDrawer open={goLiveOpen} onClose={() => setGoLiveOpen(false)} />
    </>
  )
}
