import { type ButtonHTMLAttributes, forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-semibold transition-all duration-150 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 disabled:active:scale-100 cursor-pointer disabled:cursor-not-allowed [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary: 'bg-ink-900 text-white hover:bg-ink-800',
        accent: 'bg-primary-500 text-white hover:bg-primary-600',
        secondary: 'bg-ink-100 text-ink-900 hover:bg-ink-200',
        outline: 'border border-ink-200 bg-transparent text-ink-900 hover:bg-ink-50',
        ghost: 'bg-transparent text-ink-700 hover:bg-ink-100',
        destructive: 'bg-danger text-danger-foreground hover:bg-danger/90',
        link: 'bg-transparent text-primary-600 underline-offset-4 hover:underline rounded-none px-0',
      },
      size: {
        sm: 'h-9 px-4 text-sm',
        md: 'h-11 px-6 text-base',
        lg: 'h-[3.25rem] px-8 text-base',
        icon: 'h-11 w-11 shrink-0 rounded-full',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
        {children}
      </button>
    )
  },
)
Button.displayName = 'Button'
