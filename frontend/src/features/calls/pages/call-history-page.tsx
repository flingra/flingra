import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Phone, PhoneIncoming, PhoneMissed, PhoneOutgoing, Video } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { PageSpinner } from '@/components/ui/spinner'
import { useToast } from '@/components/ui/toast'
import { CallScreen } from '@/features/calls/components/call-screen'
import { MessagesTabs } from '@/features/messages/components/messages-tabs'
import { ApiError } from '@/lib/api/types'
import { listCallHistory, startCall, type CallHistoryItem } from '@/lib/api/calls'

const STATUS_LABELS: Record<CallHistoryItem['status'], string> = {
  completed: 'Completed',
  missed: 'Missed',
  'no-answer': 'No answer',
  declined: 'Declined',
}

function formatCallDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}:${remainder.toString().padStart(2, '0')}`
}

export function CallHistoryPage() {
  const { showToast } = useToast()
  const [callingId, setCallingId] = useState<string | null>(null)
  const [activeCall, setActiveCall] = useState<{ callId: string; profile: CallHistoryItem; mode: 'video' | 'voice' } | null>(null)
  const { data: calls = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['call-history'],
    queryFn: listCallHistory,
  })

  async function handleCallBack(call: CallHistoryItem) {
    setCallingId(call.callId)
    try {
      const session = await startCall(call.participantId, call.callType)
      setActiveCall({
        callId: session.callId,
        profile: call,
        mode: call.callType === 'audio' ? 'voice' : 'video',
      })
    } catch (error) {
      showToast({
        title: 'Could not call this member',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setCallingId(null)
    }
  }

  return (
    <section className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-2xl font-bold text-ink-900">Messages</h1>
        <p className="mt-1 text-sm text-ink-500">Your conversations and call history.</p>
      </header>
      <MessagesTabs />
      <h2 className="mb-3 text-lg font-semibold text-ink-900">Call history</h2>

      {isLoading && <PageSpinner label="Loading call history" />}
      {isError && (
        <ErrorState title="Couldn't load call history" action={{ label: 'Try again', onClick: () => void refetch() }} />
      )}
      {!isLoading && !isError && calls.length === 0 && (
        <EmptyState title="No calls yet" description="Your incoming and outgoing calls will appear here." />
      )}
      {calls.length > 0 && (
        <div className="divide-y divide-ink-100 overflow-hidden rounded-2xl border border-ink-100 bg-white">
          {calls.map((call) => {
            const CallDirectionIcon = call.status === 'missed'
              ? PhoneMissed
              : call.direction === 'incoming'
                ? PhoneIncoming
                : PhoneOutgoing

            return (
              <article key={call.callId} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                <Avatar name={call.participantName} src={call.participantPhoto ?? undefined} size="md" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink-900">{call.participantName}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-500">
                    <span className={`inline-flex items-center gap-1 ${call.status === 'missed' || call.status === 'no-answer' ? 'text-danger' : ''}`}>
                      <CallDirectionIcon className="size-4" aria-hidden="true" />
                      {STATUS_LABELS[call.status]}
                    </span>
                    <span aria-hidden="true">·</span>
                    <span className="inline-flex items-center gap-1">
                      {call.callType === 'video' ? <Video className="size-4" aria-hidden="true" /> : <Phone className="size-4" aria-hidden="true" />}
                      {call.callType === 'video' ? 'Video' : 'Voice'}
                    </span>
                    {call.status === 'completed' && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span>{formatDuration(call.durationSeconds)}</span>
                      </>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-ink-400">{formatCallDate(call.createdAt)}</p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="w-full sm:w-auto"
                  loading={callingId === call.callId}
                  disabled={callingId !== null || activeCall !== null}
                  onClick={() => void handleCallBack(call)}
                >
                  <PhoneIncoming className="size-4" aria-hidden="true" /> Call back
                </Button>
              </article>
            )
          })}
        </div>
      )}

      {activeCall && (
        <CallScreen
          callId={activeCall.callId}
          mode={activeCall.mode}
          profile={{
            id: activeCall.profile.participantId,
            displayName: activeCall.profile.participantName,
            photos: activeCall.profile.participantPhoto ? [activeCall.profile.participantPhoto] : [],
            identity: activeCall.profile.participantIdentity,
          }}
          onEnd={() => {
            setActiveCall(null)
            void refetch()
          }}
        />
      )}
    </section>
  )
}
