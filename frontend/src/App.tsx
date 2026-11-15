import { useEffect } from 'react'
import { AppProviders } from './app/providers'
import { AppRouter } from './app/router'
import { Preloader } from './components/preloader'
import { restoreSession } from './lib/api/auth'
import { useSessionStore } from './lib/stores/session-store'
import { useAdminStore } from './lib/stores/admin-store'

export default function App() {
  const setSession = useSessionStore((state) => state.setSession)
  const setHydrated = useSessionStore((state) => state.setHydrated)
  const restoreAdmin = useAdminStore((state) => state.restore)

  useEffect(() => {
    restoreSession()
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setHydrated(true))
  }, [setHydrated, setSession])

  useEffect(() => {
    restoreAdmin()
  }, [restoreAdmin])

  return (
    <AppProviders>
      <AppRouter />
      <Preloader />
    </AppProviders>
  )
}
