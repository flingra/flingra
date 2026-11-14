import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Gift, Mic, MicOff, MonitorUp, MonitorX, PhoneOff, Video, VideoOff, Volume2, VolumeX } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { useFocusTrap } from '@/lib/use-focus-trap'
import { useToast } from '@/components/ui/toast'
import { getOwnedGifts, simulateReceivedGift, spendOwnedGift } from '@/lib/api/wallet'
import { ApiError, type MemberProfile } from '@/lib/api/types'

const RING_DURATION_MS = 2200
/** Simulates the other party gifting back periodically, since this mock only has one real account. */
const INCOMING_GIFT_INTERVAL_MS = 15000

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function CallScreen({ profile, mode, onEnd }: { profile: MemberProfile; mode: 'video' | 'voice'; onEnd: () => void }) {
  const containerRef = useFocusTrap(true)
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [connected, setConnected] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [muted, setMuted] = useState(false)
  const [cameraOn, setCameraOn] = useState(mode === 'video')
  const [speakerOn, setSpeakerOn] = useState(true)
  const [sharingScreen, setSharingScreen] = useState(false)
  const [giftPickerOpen, setGiftPickerOpen] = useState(false)

  const { data: ownedGifts = [] } = useQuery({ queryKey: ['owned-gifts'], queryFn: getOwnedGifts, enabled: connected })

  useEffect(() => {
    const ringTimer = setTimeout(() => setConnected(true), RING_DURATION_MS)
    return () => clearTimeout(ringTimer)
  }, [])

  useEffect(() => {
    if (!connected) return
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [connected])

  // Once both sides are connected, the other party can gift back too — simulated
  // here since this mock only has one real logged-in account.
  useEffect(() => {
    if (!connected) return
    const giftTimer = setInterval(() => {
      const gift = simulateReceivedGift(profile.id, profile.displayName)
      queryClient.invalidateQueries({ queryKey: ['received-gifts'] })
      showToast({ title: `${profile.displayName} sent you ${gift.emoji} ${gift.name}`, description: 'Redeem it from your wallet.', variant: 'success' })
    }, INCOMING_GIFT_INTERVAL_MS)
    return () => clearInterval(giftTimer)
  }, [connected, profile.id, profile.displayName, queryClient, showToast])

  async function handleSendGift(giftTypeId: string) {
    setGiftPickerOpen(false)
    try {
      const gift = await spendOwnedGift(giftTypeId)
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

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onEnd()
    }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const showVideoFeed = mode === 'video' && cameraOn

  return createPortal(
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
          {connected ? formatElapsed(elapsed) : mode === 'video' ? 'Ringing video call…' : 'Ringing voice call…'}
        </p>
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

        <button
          type="button"
          onClick={onEnd}
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
    </div>,
    document.body,
  )
}
