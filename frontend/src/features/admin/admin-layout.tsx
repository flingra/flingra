import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowLeftRight, ChevronRight, ClipboardCheck, Coins, CreditCard, FileText, Gift, HeartHandshake,
  History, KeyRound, LayoutDashboard, LockKeyhole, LogOut, Menu, Newspaper, Radio, ScrollText,
  ShieldAlert, ShieldCheck, UserRound, Users, Wallet, X, type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAdminStore } from '@/lib/stores/admin-store'

type AdminRole = 'super_admin' | 'admin' | 'reviewer' | 'safety_admin' | 'auditor'
type NavItem = { to: string; label: string; icon: LucideIcon; roles: AdminRole[]; end?: boolean }
type NavGroup = { label?: string; items: NavItem[] }

const EVERYONE: AdminRole[] = ['super_admin', 'admin', 'reviewer', 'safety_admin', 'auditor']
const SUPER: AdminRole[] = ['super_admin']
const ADMIN: AdminRole[] = ['super_admin', 'admin']
const SAFETY: AdminRole[] = ['super_admin', 'admin', 'safety_admin']

const NAV: NavGroup[] = [
  {
    items: [
      { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, roles: EVERYONE, end: true },
      { to: '/admin/security', label: 'Security', icon: KeyRound, roles: EVERYONE },
    ],
  },
  {
    label: 'Moderation',
    items: [
      { to: '/admin/reviews', label: 'Reviews', icon: ClipboardCheck, roles: ['super_admin', 'admin', 'reviewer'] },
      { to: '/admin/safety-reviews', label: 'Safety reviews', icon: ShieldAlert, roles: SAFETY },
      { to: '/admin/safety-reports', label: 'Safety reports', icon: FileText, roles: SAFETY },
      { to: '/admin/content', label: 'Content', icon: Newspaper, roles: SAFETY },
      { to: '/admin/live-streams', label: 'Live streams', icon: Radio, roles: SAFETY },
      { to: '/admin/meetup-disputes', label: 'Meetup disputes', icon: HeartHandshake, roles: SUPER },
    ],
  },
  {
    label: 'People',
    items: [
      { to: '/admin/users', label: 'Members', icon: UserRound, roles: ADMIN },
      { to: '/admin/admins', label: 'Admins', icon: Users, roles: SUPER },
      { to: '/admin/privacy-requests', label: 'Privacy requests', icon: LockKeyhole, roles: SUPER },
    ],
  },
  {
    label: 'Finance',
    items: [
      { to: '/admin/payouts', label: 'Payouts', icon: Wallet, roles: SUPER },
      { to: '/admin/wallet-adjustments', label: 'Wallet adjustments', icon: ArrowLeftRight, roles: SUPER },
      { to: '/admin/coin-pricing', label: 'Coin pricing', icon: Coins, roles: SUPER },
      { to: '/admin/subscriptions', label: 'Subscriptions', icon: CreditCard, roles: SUPER },
      { to: '/admin/gifts', label: 'Gift catalog', icon: Gift, roles: SUPER },
    ],
  },
  {
    label: 'Audit',
    items: [
      { to: '/admin/audit', label: 'Audit', icon: ScrollText, roles: ['super_admin', 'safety_admin', 'auditor'], end: true },
      { to: '/admin/audit/events', label: 'Platform audit', icon: History, roles: ['super_admin', 'auditor'] },
    ],
  },
]

const roleLabel = (role: string) => role.replace(/_/g, ' ')

type SidebarProps = {
  groups: NavGroup[]
  role: string
  signingOut: boolean
  signOutFailed: boolean
  onSignOut: () => void
}

function SidebarContent({ groups, role, signingOut, signOutFailed, onSignOut }: SidebarProps) {
  return (
    <>
      <div className="flex h-16 shrink-0 items-center gap-3 border-b border-ink-100 px-5">
        <div className="grid size-9 place-items-center rounded-lg bg-primary-500 text-white">
          <ShieldCheck className="size-5" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-ink-900">Flingra</p>
          <p className="text-xs text-ink-500">Admin console</p>
        </div>
      </div>

      <nav aria-label="Admin" className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {groups.map((group, index) => (
          <div key={group.label ?? index}>
            {group.label && <p className="mb-1.5 px-3 text-xs font-medium text-ink-500">{group.label}</p>}
            <ul className="space-y-0.5">
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    end={end}
                    className={({ isActive }) =>
                      `group relative flex h-9 items-center gap-3 rounded-lg px-3 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 ${
                        isActive ? 'bg-primary-50 text-primary-700' : 'text-ink-600 hover:bg-ink-50 hover:text-ink-900'
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && <span aria-hidden className="absolute inset-y-1.5 -left-3 w-[3px] rounded-r-full bg-primary-500" />}
                        <Icon className={`size-4 shrink-0 ${isActive ? 'text-primary-600' : 'text-ink-400 group-hover:text-ink-600'}`} />
                        <span className="truncate">{label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-ink-100 p-3">
        <div className="flex items-center gap-3 px-2 py-1.5">
          <div className="grid size-9 shrink-0 place-items-center rounded-full bg-ink-100 text-ink-600">
            <UserRound className="size-4" />
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            {/* If your session has a name or email, show it here and move the role to the second line. */}
            <p className="truncate text-sm font-medium capitalize text-ink-900">{roleLabel(role)}</p>
            <p className="text-xs text-ink-500">{signingOut ? 'Signing out…' : 'Signed in'}</p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Sign out" title="Sign out" onClick={onSignOut} disabled={signingOut}>
            <LogOut className="size-4" />
          </Button>
        </div>
        {signOutFailed && <p role="alert" className="px-2 pt-1 text-xs text-red-600">Couldn’t sign out. Try again.</p>}
      </div>
    </>
  )
}

export function AdminLayout() {
  const session = useAdminStore((state) => state.session)
  const logout = useAdminStore((state) => state.logout)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [signOutFailed, setSignOutFailed] = useState(false)

  const role = session?.role as AdminRole | undefined

  const groups = useMemo(
    () =>
      role
        ? NAV.map((group) => ({ ...group, items: group.items.filter((item) => item.roles.includes(role)) })).filter(
            (group) => group.items.length > 0,
          )
        : [],
    [role],
  )

  // The most specific nav item that matches the URL drives the breadcrumb.
  const current = useMemo(() => {
    const path = pathname.replace(/\/+$/, '') || '/'
    return groups
      .flatMap((group) => group.items.map((item) => ({ ...item, group: group.label })))
      .filter((item) => path === item.to || (item.to !== '/admin' && path.startsWith(`${item.to}/`)))
      .sort((a, b) => b.to.length - a.to.length)[0]
  }, [groups, pathname])

  useEffect(() => {
    setDrawerOpen(false)
  }, [pathname])

  useEffect(() => {
    if (!drawerOpen) return
    const onKeyDown = (event: KeyboardEvent) => event.key === 'Escape' && setDrawerOpen(false)
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [drawerOpen])

  async function handleSignOut() {
    setSigningOut(true)
    setSignOutFailed(false)
    try {
      await logout()
      navigate('/admin/login', { replace: true })
    } catch {
      setSignOutFailed(true)
    } finally {
      setSigningOut(false)
    }
  }

  if (!session) return null

  const sidebar = (
    <SidebarContent groups={groups} role={session.role} signingOut={signingOut} signOutFailed={signOutFailed} onSignOut={handleSignOut} />
  )

  return (
    <div className="admin-layout min-h-screen bg-ink-50 text-ink-900 lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-ink-100 bg-white lg:flex">{sidebar}</aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col bg-white shadow-xl">
            {sidebar}
            <Button variant="ghost" size="icon" className="absolute right-3 top-3.5" aria-label="Close navigation" onClick={() => setDrawerOpen(false)}>
              <X className="size-5" />
            </Button>
          </aside>
        </div>
      )}

      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-ink-100 bg-white/80 px-4 backdrop-blur sm:px-6 lg:px-8">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" aria-expanded={drawerOpen} onClick={() => setDrawerOpen(true)}>
            <Menu className="size-5" />
          </Button>
          <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
            <span className="text-ink-500">Admin</span>
            {current?.group && (
              <>
                <ChevronRight className="size-3.5 shrink-0 text-ink-400" />
                <span className="text-ink-500">{current.group}</span>
              </>
            )}
            {current && (
              <>
                <ChevronRight className="size-3.5 shrink-0 text-ink-400" />
                <span className="truncate font-medium text-ink-900">{current.label}</span>
              </>
            )}
          </nav>
          <span className="rounded-full border border-primary-100 bg-primary-50 px-2.5 py-1 text-xs font-medium capitalize text-primary-700">
            {roleLabel(session.role)}
          </span>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}