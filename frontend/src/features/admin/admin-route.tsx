import { Navigate, Outlet } from 'react-router-dom'
import { useAdminStore } from '@/lib/stores/admin-store'

export function AdminRoute() {
  const { session, hydrated } = useAdminStore()
  if (!hydrated) return <div className="flex min-h-screen items-center justify-center text-sm text-ink-500">Loading admin session...</div>
  return session ? <Outlet /> : <Navigate to="/admin/login" replace />
}
