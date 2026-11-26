import { Outlet, useLocation } from 'react-router-dom'
import { Header } from '@/components/layout/header'
import { Footer } from '@/components/layout/footer'
import { BottomNav } from '@/components/layout/bottom-nav'
import { IncomingCallListener } from '@/features/calls/components/incoming-call-listener'
import { useSessionStore } from '@/lib/stores/session-store'
import { cn } from '@/lib/utils'

// Pre-access routes: the user hasn't verified themselves into the app yet, so the
// header stays minimal (just a centered logo, no nav/account chrome) and the page
// fills the screen with no footer, matching the rest of this gated flow.
const FULLSCREEN_ROUTES = new Set(['/', '/login', '/signup', '/verify-contact', '/password/forgot', '/password/reset'])

export function ShellLayout() {
  const session = useSessionStore((state) => state.session)
  const signedIn = session?.stage === 'active'
  const location = useLocation()
  const fullscreen = FULLSCREEN_ROUTES.has(location.pathname)

  return (
    <div className={cn('flex min-h-dvh flex-col bg-ink-50', fullscreen && 'h-dvh overflow-hidden')}>
      <Header minimal={fullscreen} />
      <main className={cn('flex-1', signedIn && 'pb-28', fullscreen && 'overflow-hidden')}>
        <div key={location.pathname} className={cn('animate-page-enter', fullscreen && 'h-full')}>
          <Outlet />
        </div>
      </main>
      {!signedIn && !fullscreen && <Footer />}
      {signedIn && <BottomNav />}
      {signedIn && <IncomingCallListener />}
    </div>
  )
}
