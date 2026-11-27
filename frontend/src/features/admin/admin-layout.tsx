import { useEffect, useState } from 'react'
import type { ReactNode, SelectHTMLAttributes } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api/types'

/* ---------- formatting ---------- */

export function humanize(value: string) {
  const text = value.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

/* ---------- feedback banners ---------- */

const ALERT_STYLES = {
  error: { box: 'border-red-200 bg-red-50 text-red-800', dot: 'bg-red-500' },
  success: { box: 'border-emerald-200 bg-emerald-50 text-emerald-800', dot: 'bg-emerald-500' },
}

export function Alert({ tone, children, onDismiss }: { tone: 'error' | 'success'; children: ReactNode; onDismiss?: () => void }) {
  const style = ALERT_STYLES[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${style.box}`}>
      <span aria-hidden className={`mt-1.5 size-2 shrink-0 rounded-full ${style.dot}`} />
      <div className="min-w-0 flex-1">{children}</div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="rounded px-1.5 text-xs font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current">
          Dismiss
        </button>
      )}
    </div>
  )
}

export function useFeedback() {
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const clear = () => { setError(null); setNotice(null) }
  const notify = (message: string) => { setError(null); setNotice(message) }
  const fail = (e: unknown, fallback: string) => { setNotice(null); setError(e instanceof ApiError ? e.message : fallback) }
  const banner = error || notice ? (
    <div className="space-y-2">
      {error && <Alert tone="error" onDismiss={() => setError(null)}>{error}</Alert>}
      {notice && <Alert tone="success" onDismiss={() => setNotice(null)}>{notice}</Alert>}
    </div>
  ) : null
  return { error, clear, notify, fail, banner }
}

/* ---------- confirmation dialog ---------- */

type ConfirmOptions = { title: string; description?: ReactNode; confirmLabel?: string; tone?: 'default' | 'danger' }

export function useConfirm() {
  const [pending, setPending] = useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null)

  const confirm = (options: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...options, resolve }))
  const close = (ok: boolean) => { pending?.resolve(ok); setPending(null) }

  useEffect(() => {
    if (!pending) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { pending.resolve(false); setPending(null) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [pending])

  const dialog = pending ? (
    <div className="fixed inset-0 z-50 grid place-items-center p-4" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="absolute inset-0 bg-black/40" onClick={() => close(false)} />
      <div className="relative w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 id="confirm-title" className="text-base font-semibold text-ink-900">{pending.title}</h2>
        {pending.description && <div className="mt-2 text-sm text-ink-600">{pending.description}</div>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" autoFocus onClick={() => close(false)}>Cancel</Button>
          <Button variant={pending.tone === 'danger' ? 'destructive' : 'default'} onClick={() => close(true)}>{pending.confirmLabel ?? 'Confirm'}</Button>
        </div>
      </div>
    </div>
  ) : null

  return { confirm, dialog }
}

/* ---------- layout pieces ---------- */

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-ink-500">{description}</p>}
      </div>
      {actions}
    </header>
  )
}

export function Panel({ title, description, actions, flush, className = '', children }: {
  title?: string; description?: string; actions?: ReactNode; flush?: boolean; className?: string; children: ReactNode
}) {
  return (
    <section className={`overflow-hidden rounded-xl border border-ink-100 bg-white ${className}`}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink-900">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-ink-500">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={flush ? '' : 'p-5'}>{children}</div>
    </section>
  )
}

export function Field({ label, hint, className = '', children }: { label: string; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={className}>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-ink-900">{label}</span>
        {children}
      </label>
      {hint && <p className="mt-1.5 text-xs text-ink-500">{hint}</p>}
    </div>
  )
}

export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`h-10 w-full rounded-lg border border-ink-200 bg-white px-3 text-sm text-ink-900 outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${className}`}
    />
  )
}

export function Segmented<T extends string>({ label, value, onChange, options }: {
  label: string; value: T; onChange: (value: T) => void; options: { value: T; label: string }[]
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg bg-ink-100 p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 ${
            value === option.value ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-600 hover:text-ink-900'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/* ---------- tables ---------- */

export function Table({ head, actions, children }: { head: string[]; actions?: boolean; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-ink-100 bg-ink-50 text-xs text-ink-500">
            {head.map((label, index) => (
              <th key={label} scope="col" className={`px-5 py-3 font-medium ${actions && index === head.length - 1 ? 'text-right' : ''}`}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">{children}</tbody>
      </table>
    </div>
  )
}

export function Td({ right, className = '', children }: { right?: boolean; className?: string; children: ReactNode }) {
  return <td className={`px-5 py-3.5 align-middle ${right ? 'text-right' : ''} ${className}`}>{children}</td>
}

/* ---------- badges ---------- */

type Tone = 'neutral' | 'success' | 'warning' | 'danger'
const TONES: Record<Tone, string> = {
  neutral: 'bg-ink-100 text-ink-600',
  success: 'bg-emerald-50 text-emerald-700',
  warning: 'bg-amber-50 text-amber-700',
  danger: 'bg-red-50 text-red-700',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {children}
    </span>
  )
}

const GOOD = new Set(['active', 'approved', 'completed', 'enabled', 'reviewed', 'success', 'verified'])
const WARN = new Set(['in_review', 'initiating', 'pending', 'processing', 'queued', 'suspended'])
const BAD = new Set(['banned', 'declined', 'denied', 'disputed', 'failed', 'failure', 'rejected', 'reversed'])

export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-ink-400">—</span>
  const key = status.toLowerCase()
  const tone: Tone = GOOD.has(key) ? 'success' : WARN.has(key) ? 'warning' : BAD.has(key) ? 'danger' : 'neutral'
  return <Badge tone={tone}>{humanize(status)}</Badge>
}

/* ---------- loading and empty states ---------- */

export function EmptyState({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-ink-200 bg-white px-6 py-14 text-center">
      <div className="mb-3 grid size-10 place-items-center rounded-full bg-ink-100 text-ink-500"><Icon className="size-5" /></div>
      <p className="text-sm font-medium text-ink-900">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-ink-500">{description}</p>}
    </div>
  )
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" className="divide-y divide-ink-100 rounded-xl border border-ink-100 bg-white">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center justify-between gap-6 px-5 py-4">
          <div className="space-y-2">
            <div className="h-3.5 w-40 animate-pulse rounded bg-ink-100" />
            <div className="h-3 w-56 animate-pulse rounded bg-ink-100" />
          </div>
          <div className="h-8 w-20 animate-pulse rounded-lg bg-ink-100" />
        </div>
      ))}
    </div>
  )
}

/** Shows a skeleton while loading, the empty state when there are no rows (and no error), otherwise the content. */
export function Async({ loading, count, failed, empty, children }: { loading: boolean; count: number; failed?: boolean; empty: ReactNode; children: ReactNode }) {
  if (loading) return <ListSkeleton />
  if (count === 0) return failed ? null : <>{empty}</>
  return <>{children}</>
}

/* ---------- misc ---------- */

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }
  return <Button type="button" size="sm" variant="outline" onClick={() => void copy()}>{copied ? 'Copied' : 'Copy'}</Button>
}