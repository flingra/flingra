import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface AuthPageShellProps {
  title: string
  subtitle?: string
  children: ReactNode
  footer?: ReactNode
  maxWidth?: string
}

export function AuthPageShell({ title, subtitle, children, footer, maxWidth = 'max-w-md' }: AuthPageShellProps) {
  return (
    <div className="relative flex h-full flex-col items-center justify-center overflow-y-auto px-4 py-6 sm:px-6 sm:py-10">
      <span
        className="pointer-events-none absolute -left-20 -top-20 size-64 animate-pulse rounded-full bg-primary-200/40 blur-3xl"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute -bottom-24 -right-20 size-72 animate-pulse rounded-full bg-primary-300/30 blur-3xl"
        style={{ animationDelay: '1s' }}
        aria-hidden="true"
      />

      <div className={cn('relative w-full animate-auth-in', maxWidth)}>
        <div className="text-center">
          <h1 className="text-2xl font-bold text-ink-900 sm:text-3xl">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-ink-500">{subtitle}</p>}
        </div>
        <div className="mt-6">{children}</div>
        {footer && <div className="mt-6 text-center text-sm text-ink-500">{footer}</div>}
      </div>
    </div>
  )
}
