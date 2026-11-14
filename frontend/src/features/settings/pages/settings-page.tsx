import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Crown, LogOut, Lock, Shield, User, Wallet, BadgeCheck } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { signOut } from '@/lib/api/auth'
import { getOwnProfile } from '@/lib/api/profiles'
import { useSessionStore } from '@/lib/stores/session-store'

const ROWS = [
  { to: '/settings/profile', icon: User, label: 'Profile' },
  { to: '/settings/verification', icon: BadgeCheck, label: 'Verification' },
  { to: '/settings/security', icon: Lock, label: 'Security' },
  { to: '/settings/privacy', icon: Shield, label: 'Privacy & data' },
  { to: '/wallet', icon: Wallet, label: 'Wallet & payments' },
]

export function SettingsPage() {
  const navigate = useNavigate()
  const session = useSessionStore((state) => state.session)
  const setSession = useSessionStore((state) => state.setSession)
  const { data: profile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, retry: false })

  async function handleSignOut() {
    await signOut()
    setSession(null)
    navigate('/login')
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Settings</h1>

      <div className="mt-6 flex items-center gap-4 rounded-3xl border border-ink-100 bg-white p-6 shadow-soft">
        <Avatar name={profile?.displayName ?? 'Me'} src={profile?.photos[0]} size="lg" />
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate text-lg font-semibold text-ink-900">
            {profile?.displayName ?? session?.maskedContact}
            {profile?.subscriptionTier === 'vip' && (
              <span className="flex shrink-0 items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700">
                <Crown className="size-3" aria-hidden="true" /> VIP
              </span>
            )}
          </p>
          <p className="truncate text-sm text-ink-500">{session?.maskedContact}</p>
          <p className="mt-1 inline-flex items-center gap-1.5 text-sm font-medium text-success">
            <span className="size-1.5 rounded-full bg-success" aria-hidden="true" /> Account active
          </p>
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
        {ROWS.map(({ to, icon: Icon, label }, index) => (
          <Link
            key={to}
            to={to}
            className={`flex items-center gap-3 px-5 py-4 transition-colors hover:bg-ink-50 ${index < ROWS.length - 1 ? 'border-b border-ink-100' : ''}`}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="flex-1 font-medium text-ink-800">{label}</span>
            <ChevronRight className="size-4 text-ink-300" aria-hidden="true" />
          </Link>
        ))}
      </div>

      <Button variant="outline" className="mt-6 w-full text-danger" onClick={handleSignOut}>
        <LogOut className="size-4" aria-hidden="true" /> Sign out
      </Button>
    </div>
  )
}
