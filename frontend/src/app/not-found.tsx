import { Link } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function NotFound() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 px-4 py-24 text-center">
      <p className="text-sm font-semibold text-primary-600">404</p>
      <h1 className="text-2xl font-bold text-ink-900">We couldn't find that page</h1>
      <p className="text-ink-500">The link may be broken, or the page may have moved.</p>
      <Link to="/" className={cn(buttonVariants({ variant: 'primary' }), 'mt-2')}>
        Go home
      </Link>
    </div>
  )
}
