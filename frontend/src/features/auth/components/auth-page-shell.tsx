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
    <div className="flex min-h-[calc(100dvh-4rem)] flex-col items-center justify-center px-4 py-12 sm:px-6">
      <div className={cn('w-full animate-auth-in', maxWidth)}>
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
