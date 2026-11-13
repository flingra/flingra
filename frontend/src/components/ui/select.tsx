import { type SelectHTMLAttributes, forwardRef } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <span className="relative block">
        <select
          ref={ref}
          className={cn(
            'h-12 w-full appearance-none rounded-2xl border border-transparent bg-ink-50 px-4 pr-10 text-base text-ink-900 transition-colors focus-visible:border-primary-400 focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 disabled:cursor-not-allowed disabled:opacity-50',
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute right-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-400"
        />
      </span>
    )
  },
)
Select.displayName = 'Select'
