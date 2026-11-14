import { Outlet, useLocation } from 'react-router-dom'
import { Header } from '@/components/layout/header'
import { Footer } from '@/components/layout/footer'
import { BottomNav } from '@/components/layout/bottom-nav'
import { useSessionStore } from '@/lib/stores/session-store'
import { cn } from '@/lib/utils'

const FULLSCREEN_ROUTES = new Set(['/', '/login', '/signup'])

export function ShellLayout() {
  const session = useSessionStore((state) => state.session)
  const signedIn = session?.stage === 'active'
  const location = useLocation()
  const fullscreen = FULLSCREEN_ROUTES.has(location.pathname)

  return (
    <div className={cn('flex min-h-dvh flex-col bg-ink-50', fullscreen && 'h-dvh overflow-hidden')}>
      <Header />
      <main className={cn('flex-1', signedIn && 'pb-28', fullscreen && 'overflow-hidden')}>
        <div key={location.pathname} className={cn('animate-page-enter', fullscreen && 'h-full')}>
          <Outlet />
        </div>
      </main>
      {!signedIn && !fullscreen && <Footer />}
      {signedIn && <BottomNav />}
    </div>
  )
}
