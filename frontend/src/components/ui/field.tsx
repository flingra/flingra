import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface FieldProps {
  id: string
  label: string
  optional?: boolean
  hint?: string
  error?: string
  className?: string
  children: ReactNode
}

export function Field({ id, label, optional, hint, error, className, children }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = errorId ?? hintId

  const control =
    describedBy && isValidElement(children)
      ? cloneElement(children as ReactElement<{ 'aria-describedby'?: string }>, {
          'aria-describedby': describedBy,
        })
      : children

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium text-ink-800">
          {label}
        </label>
        {optional && <span className="text-xs text-ink-400">Optional</span>}
      </div>
      {control}
      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-400">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
