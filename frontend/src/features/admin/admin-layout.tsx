import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ShieldCheck, ClipboardCheck, Users, ScrollText, LogOut, Coins } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAdminStore } from '@/lib/stores/admin-store'

export function AdminLayout() {
  const session = useAdminStore((state) => state.session)
  const logout = useAdminStore((state) => state.logout)
  const navigate = useNavigate()
  if (!session) return null
  const links = [
    { to: '/admin', label: 'Reviews', icon: ClipboardCheck, roles: ['super_admin', 'reviewer'] },
    { to: '/admin/admins', label: 'Admins', icon: Users, roles: ['super_admin'] },
    { to: '/admin/audit', label: 'Audit', icon: ScrollText, roles: ['super_admin', 'safety_admin', 'auditor'] },
    { to: '/admin/coin-pricing', label: 'Coin pricing', icon: Coins, roles: ['super_admin'] },
  ].filter((link) => link.roles.includes(session.role))
  return (
    <div className="min-h-screen bg-ink-50 text-ink-900">
      <header className="border-b border-ink-100 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3"><ShieldCheck className="size-6 text-primary-500" /><strong>Flingra Admin</strong><span className="rounded-full bg-primary-50 px-3 py-1 text-xs font-semibold text-primary-700">{session.role}</span></div>
          <Button variant="ghost" size="sm" onClick={async () => { await logout(); navigate('/admin/login') }}><LogOut className="size-4" /> Sign out</Button>
        </div>
      </header>
      <div className="mx-auto grid max-w-7xl gap-6 px-6 py-8 md:grid-cols-[220px_1fr]">
        <nav className="flex gap-2 md:flex-col">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/admin'} className={({ isActive }) => `flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold ${isActive ? 'bg-primary-500 text-white' : 'text-ink-600 hover:bg-white'}`}><Icon className="size-4" />{label}</NavLink>)}</nav>
        <main><Outlet /></main>
      </div>
    </div>
  )
}
