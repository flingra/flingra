import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Phone, PhoneOff, Video as VideoIcon } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { useToast } from '@/components/ui/toast'
import { useSessionStore } from '@/lib/stores/session-store'
import { acceptCall, declineCall, listIncomingCalls } from '@/lib/api/calls'
import { ApiError } from '@/lib/api/types'
import { CallScreen, type CallParticipant } from './call-screen'

/**
 * Surfaces a real incoming call from the backend (`GET /calls/incoming`) as a private
 * accept/decline prompt, mounted once near the app root so it can interrupt any page.
 * Polling, not a push channel — the backend doesn't document a call event over the
 * existing notification websocket, so this sticks to the one documented contract.
 */
export function IncomingCallListener() {
  const signedIn = useSessionStore((state) => state.session?.stage === 'active')
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [activeCall, setActiveCall] = useState<{ callId: string; mode: 'video' | 'voice'; profile: CallParticipant } | null>(null)
  const [responding, setResponding] = useState(false)

  const { data: incoming = [] } = useQuery({
    queryKey: ['incoming-calls'],
    queryFn: listIncomingCalls,
    enabled: signedIn && !activeCall,
    refetchInterval: 4000,
  })
  const ringingCall = incoming.find((call) => call.status === 'ringing')

  async function handleAccept() {
    if (!ringingCall) return
    setResponding(true)
    try {
      const session = await acceptCall(ringingCall.callId)
      setActiveCall({
        callId: session.callId,
        mode: ringingCall.callType === 'video' ? 'video' : 'voice',
        profile: {
          id: ringingCall.callerId,
          displayName: ringingCall.callerName,
          identity: ringingCall.callerIdentity,
          photos: ringingCall.callerPhoto ? [ringingCall.callerPhoto] : [],
        },
      })
    } catch (error) {
      showToast({
        title: 'Could not accept call',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setResponding(false)
    }
  }

  async function handleDecline() {
    if (!ringingCall) return
    setResponding(true)
    try {
      await declineCall(ringingCall.callId)
      await queryClient.invalidateQueries({ queryKey: ['incoming-calls'] })
    } finally {
      setResponding(false)
    }
  }

  if (activeCall) {
    return <CallScreen callId={activeCall.callId} profile={activeCall.profile} mode={activeCall.mode} onEnd={() => setActiveCall(null)} />
  }

  if (!ringingCall) return null

  return (
    <div className="fixed inset-x-4 top-20 z-50 mx-auto flex max-w-sm items-center gap-3 rounded-3xl border border-ink-100 bg-white p-4 shadow-float">
      <Avatar name={ringingCall.callerName} src={ringingCall.callerPhoto ?? undefined} size="md" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-ink-900">{ringingCall.callerName}</p>
        <p className="text-xs text-ink-500">Incoming {ringingCall.callType === 'video' ? 'video' : 'voice'} call…</p>
      </div>
      <button
        type="button"
        onClick={handleDecline}
        disabled={responding}
        aria-label="Decline call"
        className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-full bg-danger text-white transition-colors hover:bg-danger/90 disabled:opacity-50"
      >
        <PhoneOff className="size-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={handleAccept}
        disabled={responding}
        aria-label="Accept call"
        className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-full bg-success text-white transition-colors hover:bg-success/90 disabled:opacity-50"
      >
        {ringingCall.callType === 'video' ? <VideoIcon className="size-4" aria-hidden="true" /> : <Phone className="size-4" aria-hidden="true" />}
      </button>
    </div>
  )
}
