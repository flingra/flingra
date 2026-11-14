import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Circle, Compass, Crown, MonitorPlay, Plus, Radio, Settings, ShieldCheck, Wallet } from 'lucide-react'
import { CreatePostDrawer } from '@/features/profile/components/create-post-drawer'
import { GoLiveDrawer } from '@/features/livestream/components/go-live-drawer'

const NAV_ITEMS = [
  { to: '/discover', icon: Compass, label: 'Discover' },
  { to: '/live', icon: MonitorPlay, label: 'Live' },
  { to: '/vip', icon: Crown, label: 'VIP' },
  { to: '/status', icon: Circle, label: 'Status' },
  { to: '/wallet', icon: Wallet, label: 'Wallet' },
  { to: '/safety', icon: ShieldCheck, label: 'Safety' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

// Sign out already lives in the header's account menu and in Settings — keeping
// it out of this pill too leaves room for it to fit on small phones.
export function BottomNav() {
  const [createOpen, setCreateOpen] = useState(false)
  const [goLiveOpen, setGoLiveOpen] = useState(false)

  return (
    <>
      <div className="fixed inset-x-0 bottom-3 z-30 flex items-center justify-center gap-2 px-2 sm:bottom-4 sm:gap-3 sm:px-4">
        <nav
          aria-label="Primary"
          className="flex max-w-[calc(100vw-5.5rem)] items-center gap-0.5 overflow-x-auto rounded-full bg-ink-900 px-2 py-2 shadow-float sm:max-w-none sm:gap-1 sm:px-3 sm:py-2.5"
        >
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              aria-label={label}
              className={({ isActive }) =>
                `flex size-10 shrink-0 items-center justify-center rounded-full transition-colors sm:size-11 ${
                  isActive ? 'bg-white text-ink-900' : 'text-white/70 hover:text-white'
                }`
              }
            >
              <Icon className="size-4.5 sm:size-5" aria-hidden="true" />
            </NavLink>
          ))}
          <button
            type="button"
            onClick={() => setGoLiveOpen(true)}
            aria-label="Go live"
            className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-full text-white/70 transition-colors hover:text-danger sm:size-11"
          >
            <Radio className="size-4.5 sm:size-5" aria-hidden="true" />
          </button>
        </nav>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          aria-label="Create post"
          className="flex size-12 shrink-0 cursor-pointer items-center justify-center rounded-full bg-primary-500 text-white shadow-float transition-colors hover:bg-primary-600 sm:size-14"
        >
          <Plus className="size-5 sm:size-6" aria-hidden="true" />
        </button>
      </div>

      <CreatePostDrawer open={createOpen} onClose={() => setCreateOpen(false)} />
      <GoLiveDrawer open={goLiveOpen} onClose={() => setGoLiveOpen(false)} />
    </>
  )
}
