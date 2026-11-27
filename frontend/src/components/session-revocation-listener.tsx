import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/ui/toast'
import { clearCachedSession } from '@/lib/api/auth'
import { SESSION_INVALIDATED_EVENT } from '@/lib/api/client'
import { useSessionStore } from '@/lib/stores/session-store'

export function SessionRevocationListener() {
  const session = useSessionStore((state) => state.session)
  const setSession = useSessionStore((state) => state.setSession)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  useEffect(() => {
    if (!session) return

    let handled = false
    const handleSessionInvalidated = () => {
      if (handled) return
      handled = true
      clearCachedSession()
      setSession(null)
      queryClient.clear()
      navigate('/login', { replace: true })
      showToast({
        title: 'Session ended',
        description: 'Your session was revoked. Sign in again to continue.',
        variant: 'info',
      })
    }

    window.addEventListener(SESSION_INVALIDATED_EVENT, handleSessionInvalidated)
    return () => window.removeEventListener(SESSION_INVALIDATED_EVENT, handleSessionInvalidated)
  }, [navigate, queryClient, session, setSession, showToast])

  return null
}
