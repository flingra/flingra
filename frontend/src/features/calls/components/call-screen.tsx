import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Coins, Gift, HeartHandshake, Mic, MicOff, MonitorUp, MonitorX, PhoneOff, Video, VideoOff, Volume2, VolumeX } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useFocusTrap } from '@/lib/use-focus-trap'
import { useToast } from '@/components/ui/toast'
import { getOwnProfile } from '@/lib/api/profiles'
import { getOwnedGifts, spendOwnedGift } from '@/lib/api/wallet'
import {
  CALL_CREDIT_TICK_SECONDS,
  endCall,
  getCall,
  getCallCreditBalance,
  heartbeatCall,
  LOW_CREDIT_WARNING_THRESHOLD,
  markCallConnected,
} from '@/lib/api/calls'
import { getOrCreateThread, proposePaymentInChat } from '@/lib/api/chat'
import { ApiError, type MemberProfile } from '@/lib/api/types'

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function CallScreen({
  callId,
  profile,
  mode,
  onEnd,
}: {
  callId: string
  profile: MemberProfile
  mode: 'video' | 'voice'
  onEnd: () => void
}) {
  const containerRef = useFocusTrap(true)
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [elapsed, setElapsed] = useState(0)
  const [muted, setMuted] = useState(false)
  const [cameraOn, setCameraOn] = useState(mode === 'video')
  const [speakerOn, setSpeakerOn] = useState(true)
  const [sharingScreen, setSharingScreen] = useState(false)
  const [giftPickerOpen, setGiftPickerOpen] = useState(false)
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [proposingPayment, setProposingPayment] = useState(false)
  const endedRef = useRef(false)
  const confirmedConnectionRef = useRef(false)
  const lowCreditWarnedRef = useRef(false)

  // Authoritative call status lives on the backend — this is the one source of
  // truth for ringing → active → declined/ended, not local component state.
  const { data: call } = useQuery({
    queryKey: ['call', callId],
    queryFn: () => getCall(callId),
    refetchInterval: 2000,
  })
  const status = call?.status
  const connected = status === 'active'

  const { data: ownedGifts = [] } = useQuery({ queryKey: ['owned-gifts'], queryFn: getOwnedGifts, enabled: connected })
  const { data: ownProfile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, retry: false })
  const canProposePayment = ownProfile?.identity === 'man' && profile.identity === 'woman'

  // Only male accounts spend call credits — the same asymmetric economy as meetup
  // payments (men pay, women earn free). The balance and low/out-of-credit
  // notices below are local component state, so only the caller themselves ever
  // sees them — nothing is broadcast to the other party.
  const isPayingCaller = ownProfile?.identity === 'man'
  const { data: callCredits } = useQuery({
    queryKey: ['call-credits'],
    queryFn: getCallCreditBalance,
    enabled: isPayingCaller,
  })

  function hangUp() {
    if (endedRef.current) return
    endedRef.current = true
    void endCall(callId).catch(() => {})
    onEnd()
  }

  // No real LiveKit/WebRTC media connects here (this app never captures a real
  // camera or mic), so there's no genuine "media joined" signal to react to.
  // Once the backend has moved the call past ringing, we confirm the connection
  // ourselves after a short simulated handshake, same beat the old fake ring
  // timer used.
  useEffect(() => {
    if (!status || status === 'ringing' || confirmedConnectionRef.current) return
    if (status === 'declined' || status === 'ended') return
    confirmedConnectionRef.current = true
    const timer = setTimeout(() => {
      markCallConnected(callId)
        .then((updated) => queryClient.setQueryData(['call', callId], updated))
        .catch(() => {})
    }, 1200)
    return () => clearTimeout(timer)
  }, [status, callId, queryClient])

  useEffect(() => {
    if (endedRef.current) return
    if (status === 'declined') {
      showToast({ title: `${profile.displayName} declined`, variant: 'info' })
      hangUp()
    } else if (status === 'ended') {
      showToast({ title: 'Call ended', variant: 'info' })
      hangUp()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  useEffect(() => {
    if (!connected) return
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [connected])

  // Meters the caller's own call-credit balance via the backend heartbeat while
  // connected, warns them once it runs low, and ends the call once the backend
  // reports it exhausted — all private to this caller.
  useEffect(() => {
    if (!connected || !isPayingCaller) return
    const tick = setInterval(async () => {
      try {
        const updated = await heartbeatCall(callId)
        queryClient.setQueryData(['call', callId], updated)
        const remaining = updated.creditBalance ?? 0
        queryClient.setQueryData(['call-credits'], remaining)
        if (updated.status === 'ended' || remaining <= 0) {
          showToast({
            title: "You're out of call credits",
            description: 'This call is ending. Buy more call credits to keep talking.',
            variant: 'error',
          })
          hangUp()
          return
        }
        if (remaining <= LOW_CREDIT_WARNING_THRESHOLD && !lowCreditWarnedRef.current) {
          lowCreditWarnedRef.current = true
          showToast({
            title: 'Call credit running low',
            description: `Only ${remaining} coin${remaining === 1 ? '' : 's'} left. Buy more from the call credit store.`,
            variant: 'info',
          })
        }
      } catch {
        // A missed heartbeat isn't fatal — the next tick (or the status poll) will catch a real end-of-call state.
      }
    }, CALL_CREDIT_TICK_SECONDS * 1000)
    return () => clearInterval(tick)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, isPayingCaller, callId])

  async function handleSendGift(giftTypeId: string) {
    setGiftPickerOpen(false)
    try {
      const gift = await spendOwnedGift(giftTypeId, profile.id)
      await queryClient.invalidateQueries({ queryKey: ['owned-gifts'] })
      showToast({ title: `You sent ${gift.emoji} ${gift.name}`, variant: 'success' })
    } catch (error) {
      showToast({
        title: 'Could not send gift',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    }
  }

  async function handleProposePayment() {
    setProposingPayment(true)
    try {
      const thread = await getOrCreateThread(profile.id, profile.displayName, profile.photos[0] ?? '')
      await proposePaymentInChat(thread.id, profile.id, profile.displayName, Number(paymentAmount))
      setPaymentDialogOpen(false)
      setPaymentAmount('')
      showToast({ title: 'Proposal sent', description: `Waiting for ${profile.displayName} to respond.`, variant: 'success' })
    } catch (error) {
      showToast({
        title: 'Could not send proposal',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setProposingPayment(false)
    }
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') hangUp()
    }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Best-effort: tell the backend the call is over if this screen unmounts any
  // other way (navigation, etc.) without the hang-up button being pressed.
  useEffect(() => {
    return () => {
      if (!endedRef.current) void endCall(callId).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callId])

  const showVideoFeed = mode === 'video' && cameraOn

  return createPortal(
    <>
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      aria-label={`${mode === 'video' ? 'Video' : 'Voice'} call with ${profile.displayName}`}
      className="fixed inset-0 z-50 flex flex-col items-center justify-between bg-ink-900 text-white"
    >
      {showVideoFeed && profile.photos[0] && (
        <div
          className="absolute inset-0 scale-110 bg-cover bg-center opacity-50 blur-xl"
          style={{ backgroundImage: `url(${profile.photos[0]})` }}
          aria-hidden="true"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/60" aria-hidden="true" />

      {sharingScreen && (
        <div className="absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-primary-500 px-3 py-1 text-xs font-semibold">
          <MonitorUp className="size-3.5" aria-hidden="true" /> You're sharing your screen
        </div>
      )}

      <div className="relative z-10 flex flex-col items-center gap-3 pt-20">
        <Avatar name={profile.displayName} src={profile.photos[0]} size="xl" className="size-28 ring-4 ring-white/20" />
        <p className="text-2xl font-bold">{profile.displayName}</p>
        <p className="text-sm text-white/70">
          {connected ? formatElapsed(elapsed) : status === 'connecting' ? 'Connecting…' : mode === 'video' ? 'Ringing video call…' : 'Ringing voice call…'}
        </p>
        {isPayingCaller && callCredits !== undefined && (
          <Link
            to="/credits/shop"
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
              callCredits <= LOW_CREDIT_WARNING_THRESHOLD ? 'bg-danger/90 text-white hover:bg-danger' : 'bg-white/15 text-white hover:bg-white/25'
            }`}
          >
            <Coins className="size-3.5" aria-hidden="true" />
            {callCredits} credit{callCredits === 1 ? '' : 's'} left
          </Link>
        )}
      </div>

      <div className="relative z-10 flex flex-wrap items-center justify-center gap-3 px-4 pb-10 sm:gap-5 sm:pb-12">
        <button
          type="button"
          onClick={() => setMuted((v) => !v)}
          aria-label={muted ? 'Unmute' : 'Mute'}
          aria-pressed={muted}
          className={`flex size-12 cursor-pointer items-center justify-center rounded-full transition-colors sm:size-14 ${
            muted ? 'bg-white text-ink-900' : 'bg-white/15 text-white hover:bg-white/25'
          }`}
        >
          {muted ? <MicOff className="size-5" aria-hidden="true" /> : <Mic className="size-5" aria-hidden="true" />}
        </button>

        {mode === 'video' && (
          <button
            type="button"
            onClick={() => setCameraOn((v) => !v)}
            aria-label={cameraOn ? 'Turn camera off' : 'Turn camera on'}
            aria-pressed={!cameraOn}
            className={`flex size-12 cursor-pointer items-center justify-center rounded-full transition-colors sm:size-14 ${
              !cameraOn ? 'bg-white text-ink-900' : 'bg-white/15 text-white hover:bg-white/25'
            }`}
          >
            {cameraOn ? <Video className="size-5" aria-hidden="true" /> : <VideoOff className="size-5" aria-hidden="true" />}
          </button>
        )}

        {mode === 'video' && (
          <button
            type="button"
            onClick={() => setSharingScreen((v) => !v)}
            aria-label={sharingScreen ? 'Stop sharing your screen' : 'Share your screen'}
            aria-pressed={sharingScreen}
            className={`flex size-12 cursor-pointer items-center justify-center rounded-full transition-colors sm:size-14 ${
              sharingScreen ? 'bg-white text-ink-900' : 'bg-white/15 text-white hover:bg-white/25'
            }`}
          >
            {sharingScreen ? <MonitorX className="size-5" aria-hidden="true" /> : <MonitorUp className="size-5" aria-hidden="true" />}
          </button>
        )}

        {mode === 'video' && (
          <div className="relative">
            <button
              type="button"
              onClick={() => setGiftPickerOpen((v) => !v)}
              disabled={!connected}
              aria-label="Send a gift"
              aria-pressed={giftPickerOpen}
              className="flex size-12 cursor-pointer items-center justify-center rounded-full bg-white/15 text-white transition-colors hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-40 sm:size-14"
            >
              <Gift className="size-5" aria-hidden="true" />
            </button>
            {giftPickerOpen && (
              <div className="absolute bottom-full left-1/2 mb-3 w-56 -translate-x-1/2 rounded-2xl bg-white p-3 text-ink-900 shadow-float">
                {ownedGifts.length === 0 ? (
                  <Link to="/gifts/shop" onClick={() => setGiftPickerOpen(false)} className="block text-sm font-semibold text-primary-600 hover:underline">
                    You have no gifts. Visit the gift shop →
                  </Link>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {ownedGifts.map(({ gift, quantity }) => (
                      <button
                        key={gift.id}
                        type="button"
                        onClick={() => handleSendGift(gift.id)}
                        className="flex flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 hover:bg-ink-50"
                      >
                        <span className="text-xl">{gift.emoji}</span>
                        <span className="text-[10px] font-semibold text-ink-500">×{quantity}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {canProposePayment && (
          <button
            type="button"
            onClick={() => setPaymentDialogOpen(true)}
            disabled={!connected}
            aria-label="Propose a meetup payment"
            className="flex size-12 cursor-pointer items-center justify-center rounded-full bg-white/15 text-white transition-colors hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-40 sm:size-14"
          >
            <HeartHandshake className="size-5" aria-hidden="true" />
          </button>
        )}

        <button
          type="button"
          onClick={hangUp}
          aria-label="End call"
          className="flex size-14 cursor-pointer items-center justify-center rounded-full bg-danger text-white shadow-float transition-colors hover:bg-danger/90 sm:size-16"
        >
          <PhoneOff className="size-6" aria-hidden="true" />
        </button>

        <button
          type="button"
          onClick={() => setSpeakerOn((v) => !v)}
          aria-label={speakerOn ? 'Turn speaker off' : 'Turn speaker on'}
          aria-pressed={!speakerOn}
          className={`flex size-12 cursor-pointer items-center justify-center rounded-full transition-colors sm:size-14 ${
            !speakerOn ? 'bg-white text-ink-900' : 'bg-white/15 text-white hover:bg-white/25'
          }`}
        >
          {speakerOn ? <Volume2 className="size-5" aria-hidden="true" /> : <VolumeX className="size-5" aria-hidden="true" />}
        </button>
      </div>
    </div>

    <Dialog
      open={paymentDialogOpen}
      onClose={() => setPaymentDialogOpen(false)}
      title={`Propose a payment to ${profile.displayName}`}
      description="She has to accept before anything is charged — nothing moves until she agrees."
    >
      <div className="flex flex-col gap-4">
        <Field id="call-payment-amount" label="Amount (₦)">
          <Input
            id="call-payment-amount"
            type="number"
            min={100}
            value={paymentAmount}
            onChange={(event) => setPaymentAmount(event.target.value)}
          />
        </Field>
        <Button
          loading={proposingPayment}
          disabled={!paymentAmount || Number(paymentAmount) <= 0}
          onClick={handleProposePayment}
        >
          Send proposal
        </Button>
      </div>
    </Dialog>
    </>,
    document.body,
  )
}
