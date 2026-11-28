import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Circle, Compass, MessageCircle, MonitorPlay, Plus, Wallet } from 'lucide-react'
import { CreatePostDrawer } from '@/features/profile/components/create-post-drawer'

const NAV_ITEMS = [
  { to: '/discover', icon: Compass, label: 'Discover', match: ['/discover', '/profiles'] },
  { to: '/status', icon: Circle, label: 'Status', match: ['/status'] },
  { to: '/live', icon: MonitorPlay, label: 'Live', match: ['/live'] },
  { to: '/messages', icon: MessageCircle, label: 'Messages', match: ['/messages'] },
  { to: '/wallet', icon: Wallet, label: 'Wallet', match: ['/wallet', '/gifts', '/referrals', '/payout', '/credits'] },
]

export function BottomNav() {
  const [createOpen, setCreateOpen] = useState(false)
  const { pathname } = useLocation()

  return (
    <>
      <div className="fixed inset-x-0 bottom-0 z-30 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 sm:bottom-4 sm:px-4 sm:pb-0 sm:pt-0">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-1.5 rounded-2xl border border-ink-100 bg-white/95 p-2 shadow-float backdrop-blur sm:justify-center sm:rounded-full sm:border-0 sm:bg-ink-900 sm:p-2">
          <nav
            aria-label="Primary navigation"
            className="flex min-w-0 flex-1 items-stretch justify-around sm:flex-none sm:gap-1"
          >
            {NAV_ITEMS.map(({ to, icon: Icon, label, match }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/messages'}
                aria-label={label}
                className="flex min-w-0 flex-1 sm:flex-none"
              >
                {({ isActive }) => {
                  const pathMatches = match.some((path) => pathname === path || pathname.startsWith(`${path}/`))
                  const active = isActive || pathMatches
                  return (
                    <span
                      className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-1 py-1.5 transition-colors sm:min-w-[5.5rem] sm:flex-row sm:gap-2 sm:rounded-full sm:px-3 sm:py-2.5 ${
                        active
                          ? 'bg-primary-50 text-primary-700 sm:bg-white sm:text-ink-900'
                          : 'text-ink-500 hover:text-ink-900 sm:text-white/70 sm:hover:text-white'
                      }`}
                    >
                      <Icon className="size-5 shrink-0" aria-hidden="true" />
                      <span className="truncate text-[10px] font-medium leading-none sm:text-xs">{label}</span>
                    </span>
                  )
                }}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            aria-label="Create post"
            className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-xl bg-primary-500 text-white shadow-soft transition-colors hover:bg-primary-600 sm:rounded-full"
          >
            <Plus className="size-5" aria-hidden="true" />
          </button>
        </div>
      </div>

      <CreatePostDrawer open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  )
}
