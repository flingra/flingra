import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Mic, MicOff, PhoneOff, Video, VideoOff, Volume2, VolumeX } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { useFocusTrap } from '@/lib/use-focus-trap'
import type { MemberProfile } from '@/lib/api/types'

const RING_DURATION_MS = 2200

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function CallScreen({ profile, mode, onEnd }: { profile: MemberProfile; mode: 'video' | 'voice'; onEnd: () => void }) {
  const containerRef = useFocusTrap(true)
  const [connected, setConnected] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [muted, setMuted] = useState(false)
  const [cameraOn, setCameraOn] = useState(mode === 'video')
  const [speakerOn, setSpeakerOn] = useState(true)

  useEffect(() => {
    const ringTimer = setTimeout(() => setConnected(true), RING_DURATION_MS)
    return () => clearTimeout(ringTimer)
  }, [])

  useEffect(() => {
    if (!connected) return
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [connected])

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

      <div className="relative z-10 flex flex-col items-center gap-3 pt-20">
        <Avatar name={profile.displayName} src={profile.photos[0]} size="xl" className="size-28 ring-4 ring-white/20" />
        <p className="text-2xl font-bold">{profile.displayName}</p>
        <p className="text-sm text-white/70">
          {connected ? formatElapsed(elapsed) : mode === 'video' ? 'Ringing video call…' : 'Ringing voice call…'}
        </p>
      </div>

      <div className="relative z-10 flex items-center gap-5 pb-12">
        <button
          type="button"
          onClick={() => setMuted((v) => !v)}
          aria-label={muted ? 'Unmute' : 'Mute'}
          aria-pressed={muted}
          className={`flex size-14 cursor-pointer items-center justify-center rounded-full transition-colors ${
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
            className={`flex size-14 cursor-pointer items-center justify-center rounded-full transition-colors ${
              !cameraOn ? 'bg-white text-ink-900' : 'bg-white/15 text-white hover:bg-white/25'
            }`}
          >
            {cameraOn ? <Video className="size-5" aria-hidden="true" /> : <VideoOff className="size-5" aria-hidden="true" />}
          </button>
        )}

        <button
          type="button"
          onClick={onEnd}
          aria-label="End call"
          className="flex size-16 cursor-pointer items-center justify-center rounded-full bg-danger text-white shadow-float transition-colors hover:bg-danger/90"
        >
          <PhoneOff className="size-6" aria-hidden="true" />
        </button>

        <button
          type="button"
          onClick={() => setSpeakerOn((v) => !v)}
          aria-label={speakerOn ? 'Turn speaker off' : 'Turn speaker on'}
          aria-pressed={!speakerOn}
          className={`flex size-14 cursor-pointer items-center justify-center rounded-full transition-colors ${
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
