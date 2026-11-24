import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '@/components/ui/toast'
import { signOut } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'

export function useSignOut() {
  const [isSigningOut, setIsSigningOut] = useState(false)
  const signingOutRef = useRef(false)
  const navigate = useNavigate()
  const { showToast } = useToast()
  const setSession = useSessionStore((state) => state.setSession)

  async function signOutAndRedirect(path = '/login'): Promise<boolean> {
    if (signingOutRef.current) return false
    signingOutRef.current = true
    setIsSigningOut(true)

    try {
      await signOut()
      setSession(null)
      navigate(path, { replace: true })
      return true
    } catch (error) {
      showToast({
        title: 'Could not sign out',
        description: error instanceof ApiError ? error.message : 'Check your connection and try again.',
        variant: 'error',
      })
      return false
    } finally {
      signingOutRef.current = false
      setIsSigningOut(false)
    }
  }

  return { isSigningOut, signOutAndRedirect }
}
