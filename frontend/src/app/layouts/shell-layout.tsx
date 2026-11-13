import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/header'
import { Footer } from '@/components/layout/footer'
import { BottomNav } from '@/components/layout/bottom-nav'
import { useSessionStore } from '@/lib/stores/session-store'
import { cn } from '@/lib/utils'

export function ShellLayout() {
  const session = useSessionStore((state) => state.session)
  const signedIn = session?.stage === 'active'

  return (
    <div className="flex min-h-dvh flex-col bg-ink-50">
      <Header />
      <main className={cn('flex-1', signedIn && 'pb-28')}>
        <Outlet />
      </main>
      {!signedIn && <Footer />}
      {signedIn && <BottomNav />}
    </div>
  )
}
