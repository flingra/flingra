import { Check, X } from 'lucide-react'
import type { JoinRequest } from '@/lib/api/types'

export function JoinRequestPanel({
  requests,
  onRespond,
}: {
  requests: JoinRequest[]
  onRespond: (requestId: string, accept: boolean) => void
}) {
  if (requests.length === 0) return null

  return (
    <div className="absolute left-1/2 top-20 z-20 flex w-full max-w-xs -translate-x-1/2 flex-col gap-2 px-3">
      {requests.map((request) => (
        <div key={request.id} className="flex items-center gap-3 rounded-2xl bg-white p-3 shadow-float">
          <img src={request.requesterPhoto} alt="" className="size-10 shrink-0 rounded-full object-cover" />
          <p className="flex-1 text-sm text-ink-900">
            <span className="font-semibold">{request.requesterName}</span> wants to join
          </p>
          <button
            type="button"
            onClick={() => onRespond(request.id, true)}
            aria-label={`Accept ${request.requesterName}`}
            className="flex size-8 cursor-pointer items-center justify-center rounded-full bg-primary-500 text-white hover:bg-primary-600"
          >
            <Check className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onRespond(request.id, false)}
            aria-label={`Decline ${request.requesterName}`}
            className="flex size-8 cursor-pointer items-center justify-center rounded-full bg-ink-100 text-ink-700 hover:bg-ink-200"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  )
}
