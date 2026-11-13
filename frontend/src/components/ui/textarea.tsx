import { type TextareaHTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          'flex min-h-28 w-full rounded-2xl border border-transparent bg-ink-50 px-4 py-3 text-base text-ink-900 placeholder:text-ink-400 transition-colors focus-visible:border-primary-400 focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/20',
          className,
        )}
        {...props}
      />
    )
  },
)
Textarea.displayName = 'Textarea'
