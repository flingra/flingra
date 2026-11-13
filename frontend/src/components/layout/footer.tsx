import { Link } from 'react-router-dom'
import { Logo } from '@/components/logo'

export function Footer() {
  return (
    <footer className="border-t border-ink-100 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <Logo className="text-ink-700" />
        <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-500" aria-label="Legal and support">
          <Link to="/safety" className="hover:text-ink-900">
            Safety
          </Link>
          <Link to="/help" className="hover:text-ink-900">
            Help
          </Link>
          <Link to="/terms" className="hover:text-ink-900">
            Terms
          </Link>
          <Link to="/privacy" className="hover:text-ink-900">
            Privacy
          </Link>
        </nav>
      </div>
    </footer>
  )
}
