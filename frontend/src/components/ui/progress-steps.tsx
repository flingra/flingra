import { cn } from '@/lib/utils'

interface ProgressStepsProps {
  current: number
  total: number
  label: string
}

export function ProgressSteps({ current, total, label }: ProgressStepsProps) {
  return (
    <div>
      <p className="text-sm font-bold text-primary-600">
        {current}/{total}
      </p>
      <div
        role="progressbar"
        aria-valuenow={current}
        aria-valuemin={1}
        aria-valuemax={total}
        aria-label={label}
        className="mt-2 flex gap-1.5"
      >
        {Array.from({ length: total }).map((_, index) => (
          <span
            key={index}
            className={cn('h-1.5 flex-1 rounded-full', index < current ? 'bg-primary-500' : 'bg-ink-100')}
          />
        ))}
      </div>
    </div>
  )
}
