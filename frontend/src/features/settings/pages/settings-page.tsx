import { Link } from 'react-router-dom'
import { ChevronRight, Lock, Shield, User, BadgeCheck } from 'lucide-react'

const ROWS = [
  { to: '/settings/profile', icon: User, label: 'Profile' },
  { to: '/settings/verification', icon: BadgeCheck, label: 'Verification' },
  { to: '/settings/security', icon: Lock, label: 'Security' },
  { to: '/settings/privacy', icon: Shield, label: 'Privacy & data' },
]

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Settings</h1>
      <p className="mt-1 text-sm text-ink-500">Manage your profile and account preferences.</p>

      <div className="mt-6 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
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
    </div>
  )
}
