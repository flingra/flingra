import { cn } from '@/lib/utils'

export function Logo({ className, mark = false }: { className?: string; mark?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2 font-extrabold tracking-tight', className)}>
      <span className="relative inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-500">
        <span className="absolute left-1.5 top-1.5 size-2.5 rounded-full bg-white" />
        <span className="absolute bottom-1.5 right-1.5 size-2.5 rounded-full bg-white/60" />
      </span>
      {!mark && 'Flingra'}
    </span>
  )
}
