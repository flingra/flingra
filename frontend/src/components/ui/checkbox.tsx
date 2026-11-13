import { type InputHTMLAttributes, forwardRef } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export const Checkbox = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <span className="relative inline-flex size-5 shrink-0">
        <input
          ref={ref}
          type="checkbox"
          className={cn(
            'peer size-5 shrink-0 cursor-pointer appearance-none rounded-md border border-ink-300 bg-white transition-colors checked:border-ink-900 checked:bg-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 disabled:cursor-not-allowed disabled:opacity-50',
            className,
          )}
          {...props}
        />
        <Check
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 m-auto size-3.5 text-white opacity-0 peer-checked:opacity-100"
        />
      </span>
    )
  },
)
Checkbox.displayName = 'Checkbox'
