import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useSessionStore } from '@/lib/stores/session-store'
import type { AccountStage } from '@/lib/api/types'

const STAGE_ROUTE: Record<AccountStage, string> = {
  'needs-verification': '/verify-contact',
  'needs-onboarding': '/onboarding',
  active: '/discover',
}

export function ProtectedRoute({ allow, children }: { allow: AccountStage[]; children: ReactNode }) {
  const { session, hydrated } = useSessionStore()
  const location = useLocation()

  if (!hydrated) return null
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (!allow.includes(session.stage)) {
    return <Navigate to={STAGE_ROUTE[session.stage]} replace />
  }
  return <>{children}</>
}

export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { session, hydrated } = useSessionStore()
  if (hydrated && session?.stage === 'active') {
    return <Navigate to="/discover" replace />
  }
  return <>{children}</>
}
