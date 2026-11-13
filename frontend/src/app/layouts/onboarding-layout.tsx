import { Link, Outlet } from 'react-router-dom'
import { Logo } from '@/components/logo'

export function OnboardingLayout() {
  return (
    <div className="flex min-h-dvh flex-col bg-ink-50">
      <header className="flex h-16 items-center justify-between px-4 sm:px-6">
        <Link to="/" aria-label="Flingra home">
          <Logo className="text-ink-900" />
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-4 sm:items-center">
        <div className="w-full max-w-lg">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
