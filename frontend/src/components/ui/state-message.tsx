import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, WifiOff } from 'lucide-react'
import { Button } from './button'

interface StateMessageProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: { label: string; onClick: () => void }
}

function StateMessage({ icon, title, description, action }: StateMessageProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-3xl border border-dashed border-ink-200 px-6 py-12 text-center">
      {icon}
      <p className="text-base font-semibold text-ink-900">{title}</p>
      {description && <p className="max-w-sm text-sm text-ink-500">{description}</p>}
      {action && (
        <Button variant="secondary" size="sm" onClick={action.onClick} className="mt-1">
          {action.label}
        </Button>
      )}
    </div>
  )
}

export function EmptyState(props: Omit<StateMessageProps, 'icon'>) {
  return <StateMessage {...props} icon={<Inbox className="size-8 text-ink-300" aria-hidden="true" />} />
}

export function ErrorState({
  description = 'Something went wrong. Check your connection and try again.',
  ...props
}: Omit<StateMessageProps, 'icon'>) {
  return (
    <StateMessage
      {...props}
      description={description}
      icon={<AlertTriangle className="size-8 text-danger" aria-hidden="true" />}
    />
  )
}

export function OfflineState(props: Omit<StateMessageProps, 'icon'>) {
  return <StateMessage {...props} icon={<WifiOff className="size-8 text-ink-300" aria-hidden="true" />} />
}
