import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { LocalTrack, RemoteTrack, Room as LiveKitRoom } from 'livekit-client'
import { Gift, PhoneCall, RefreshCcw, UserPlus, X } from 'lucide-react'
import { PageSpinner } from '@/components/ui/spinner'
import { ErrorState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/lib/stores/session-store'
import { getOwnedGifts, spendOwnedGift } from '@/lib/api/wallet'
import { ApiError } from '@/lib/api/types'
import {
  endStream,
  getStreamToken,
  getLiveStream,
  heartbeatStream,
  leaveStream,
  listJoinRequests,
  listParticipants,
  listStreamMessages,
  listStreamViewers,
  PREVIEW_SECONDS,
  requestToJoin,
  respondToJoinRequest,
  sendStreamMessage,
} from '@/lib/api/livestream'
import { startCall } from '@/lib/api/calls'
import { type MemberProfile } from '@/lib/api/types'
import { CallScreen } from '@/features/calls/components/call-screen'
import { ChatPanel } from '../components/chat-panel'
import { ParticipantStack } from '../components/participant-stack'
import { ViewerStrip } from '../components/viewer-strip'
import { JoinRequestPanel } from '../components/join-request-panel'

export function LivePage() {
  const { streamId = '' } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const session = useSessionStore((state) => state.session)
  const queryClient = useQueryClient()

  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [joinedToChat, setJoinedToChat] = useState(false)
  const [previewSecondsLeft, setPreviewSecondsLeft] = useState(PREVIEW_SECONDS)
  const [giftPickerOpen, setGiftPickerOpen] = useState(false)
  const [ending, setEnding] = useState(false)
  const [mediaError, setMediaError] = useState<string | null>(null)
  const [roomConnected, setRoomConnected] = useState(false)
  const [retryMedia, setRetryMedia] = useState(0)
  const [localVideoTrack, setLocalVideoTrack] = useState<LocalTrack | null>(null)
  const [remoteVideoTracks, setRemoteVideoTracks] = useState<Map<string, RemoteTrack>>(() => new Map())
  const [activeCallId, setActiveCallId] = useState<string | null>(null)
  const [startingCall, setStartingCall] = useState(false)
  const roomRef = useRef<LiveKitRoom | null>(null)
  const stageVideoRef = useRef<HTMLVideoElement>(null)
  const remoteAudioRef = useRef<HTMLDivElement>(null)
  const heartbeatFailedRef = useRef(false)
  const canChatRef = useRef(false)

  const { data: stream, isLoading, isError } = useQuery({
    queryKey: ['live-stream', streamId],
    queryFn: () => getLiveStream(streamId),
    refetchInterval: 2500,
    retry: false,
  })
  const isHost = stream?.hostId === session?.accountId
  const canChat = isHost || joinedToChat

  const { data: participants = [] } = useQuery({
    queryKey: ['live-participants', streamId],
    queryFn: () => listParticipants(streamId),
    refetchInterval: 2500,
    enabled: Boolean(stream),
  })
  const isGuest = participants.some((participant) => participant.id === session?.accountId)
  const canPublish = isHost || isGuest
  const streamReady = Boolean(stream)
  const { data: viewers = [] } = useQuery({
    queryKey: ['live-viewers', streamId],
    queryFn: () => listStreamViewers(streamId),
    refetchInterval: 2500,
    enabled: Boolean(stream),
  })
  const { data: messages = [] } = useQuery({
    queryKey: ['live-messages', streamId],
    queryFn: () => listStreamMessages(streamId),
    refetchInterval: 2500,
    enabled: Boolean(stream),
  })
  const { data: joinRequests = [] } = useQuery({
    queryKey: ['live-join-requests', streamId],
    queryFn: () => listJoinRequests(streamId),
    refetchInterval: 2500,
    enabled: Boolean(stream) && isHost,
  })
  const { data: ownedGifts = [] } = useQuery({
    queryKey: ['owned-gifts'],
    queryFn: getOwnedGifts,
    enabled: Boolean(stream) && !isHost,
  })

  const focused = participants.find((p) => p.id === focusedId) ?? participants.find((p) => p.id === stream?.hostId)
  const focusedTrack = focused?.id === session?.accountId
    ? localVideoTrack
    : focused
      ? remoteVideoTracks.get(focused.id)
      : undefined

  useEffect(() => {
    if (!streamReady) return
    let cancelled = false
    let room: LiveKitRoom | null = null

    async function connect() {
      try {
        setMediaError(null)
        setRoomConnected(false)
        setLocalVideoTrack(null)
        setRemoteVideoTracks(new Map())
        heartbeatFailedRef.current = false
        const [{ Room, RoomEvent, Track }, { url, token }] = await Promise.all([
          import('livekit-client'),
          getStreamToken(streamId),
        ])
        if (cancelled) return
        room = new Room({ adaptiveStream: true, dynacast: true })
        roomRef.current = room
        room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
          if (track.kind === Track.Kind.Video) {
            setRemoteVideoTracks((current) => new Map(current).set(participant.identity, track))
          } else if (track.kind === Track.Kind.Audio) {
            const element = track.attach()
            if (element instanceof HTMLAudioElement) {
              element.autoplay = true
              element.muted = !canChatRef.current
              remoteAudioRef.current?.appendChild(element)
            }
          }
        })
        room.on(RoomEvent.TrackUnsubscribed, (track, _publication, participant) => {
          track.detach().forEach((element) => element.remove())
          if (track.kind === Track.Kind.Video) {
            setRemoteVideoTracks((current) => {
              const next = new Map(current)
              next.delete(participant.identity)
              return next
            })
          }
        })
        room.on(RoomEvent.Disconnected, () => {
          if (!cancelled) {
            setRoomConnected(false)
            setMediaError('The livestream media connection was lost.')
          }
        })
        await room.connect(url, token)
        if (canPublish) {
          await room.localParticipant.setMicrophoneEnabled(true)
          const publication = await room.localParticipant.setCameraEnabled(true)
          if (publication?.track) setLocalVideoTrack(publication.track)
        }
        if (!cancelled) setRoomConnected(true)
      } catch (error) {
        if (!cancelled) {
          setMediaError(error instanceof Error ? error.message : 'Could not connect to the livestream.')
          if (room) {
            room.removeAllListeners()
            room.disconnect()
            if (roomRef.current === room) roomRef.current = null
          }
        }
      }
    }

    void connect()
    return () => {
      cancelled = true
      if (room) {
        room.removeAllListeners()
        room.disconnect()
        if (roomRef.current === room) roomRef.current = null
      }
    }
  }, [streamId, streamReady, canPublish, retryMedia])

  useEffect(() => {
    if (!streamReady) setRoomConnected(false)
  }, [streamReady])

  useEffect(() => {
    if (!focusedTrack || !stageVideoRef.current) return
    focusedTrack.attach(stageVideoRef.current)
    return () => {
      focusedTrack.detach(stageVideoRef.current!)
    }
  }, [focusedTrack])

  useEffect(() => {
    canChatRef.current = canChat
    remoteAudioRef.current?.querySelectorAll('audio').forEach((audio) => {
      audio.muted = !canChat
    })
  }, [canChat])

  useEffect(() => {
    if (!roomConnected) return
    const tick = setInterval(() => {
      void heartbeatStream(streamId).catch((error: unknown) => {
        if (!heartbeatFailedRef.current) {
          heartbeatFailedRef.current = true
          setMediaError(error instanceof Error ? error.message : 'Could not refresh livestream presence.')
          showToast({ title: 'Livestream connection interrupted', variant: 'error' })
        }
      })
    }, 15_000)
    return () => clearInterval(tick)
  }, [roomConnected, streamId, showToast])

  // Count down the free preview for a viewer who hasn't joined the chat yet.
  useEffect(() => {
    if (isHost || joinedToChat || !stream) return
    if (previewSecondsLeft <= 0) return
    const timer = setInterval(() => setPreviewSecondsLeft((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(timer)
  }, [isHost, joinedToChat, stream, previewSecondsLeft])

  async function handleLeave() {
    if (!stream) return
    setEnding(true)
    try {
      if (isHost) await endStream(stream.id)
      else await leaveStream(stream.id)
      navigate('/discover')
    } catch (error) {
      showToast({
        title: isHost ? 'Could not end stream' : 'Could not leave stream',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setEnding(false)
    }
  }

  async function handleRespond(requestId: string, accept: boolean) {
    try {
      await respondToJoinRequest(streamId, requestId, accept)
      await queryClient.invalidateQueries({ queryKey: ['live-join-requests', streamId] })
      await queryClient.invalidateQueries({ queryKey: ['live-participants', streamId] })
    } catch (error) {
      showToast({
        title: 'Could not update join request',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    }
  }

  async function handleSend(text: string) {
    await sendStreamMessage(streamId, text)
    await queryClient.invalidateQueries({ queryKey: ['live-messages', streamId] })
  }

  async function handleSendGift(giftTypeId: string) {
    setGiftPickerOpen(false)
    try {
      if (!stream) return
      const gift = await spendOwnedGift(giftTypeId, stream.hostId)
      await sendStreamMessage(streamId, `sent ${gift.name}`, 'gift', gift.id)
      await queryClient.invalidateQueries({ queryKey: ['live-messages', streamId] })
      await queryClient.invalidateQueries({ queryKey: ['owned-gifts'] })
      showToast({ title: `You sent ${gift.emoji} ${gift.name}`, variant: 'success' })
    } catch (err) {
      showToast({
        title: 'Could not send gift',
        description: err instanceof ApiError ? err.message : 'Try again.',
        variant: 'error',
      })
    }
  }

  async function handleRequestJoinStream() {
    try {
      await requestToJoin(streamId)
      showToast({ title: 'Request sent', description: 'The host will see your request to join.', variant: 'success' })
    } catch (error) {
      showToast({
        title: 'Could not request to join',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    }
  }

  async function handleRequestCall() {
    if (!stream || startingCall) return
    setStartingCall(true)
    try {
      const call = await startCall(stream.hostId, 'video')
      setActiveCallId(call.callId)
    } catch (error) {
      showToast({
        title: 'Could not start call',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setStartingCall(false)
    }
  }

  async function handleSwitchCamera() {
    const room = roomRef.current
    if (!room) return
    try {
      const { Track } = await import('livekit-client')
      const cameras = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === 'videoinput')
      if (cameras.length < 2) {
        showToast({ title: 'No other camera is available', variant: 'info' })
        return
      }
      const currentDevice = room.localParticipant
        .getTrackPublication(Track.Source.Camera)
        ?.track?.mediaStreamTrack.getSettings().deviceId
      const currentIndex = cameras.findIndex((device) => device.deviceId === currentDevice)
      const nextCamera = cameras[(currentIndex + 1) % cameras.length]
      const switched = await room.switchActiveDevice('videoinput', nextCamera.deviceId)
      if (!switched) throw new Error('The selected camera could not be activated.')
    } catch (error) {
      showToast({
        title: 'Could not switch camera',
        description: error instanceof Error ? error.message : 'Check camera permissions.',
        variant: 'error',
      })
    }
  }

  if (isLoading) return <PageSpinner label="Loading stream" />
  if (isError || !stream) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12">
        <ErrorState title="This stream has ended" action={{ label: 'Back to Discover', onClick: () => navigate('/discover') }} />
      </div>
    )
  }

  const showJoinGate = !isHost && !joinedToChat && previewSecondsLeft <= 0
  const hostProfile: MemberProfile = {
    id: stream.hostId,
    displayName: stream.hostName,
    bio: '',
    photos: stream.hostPhoto ? [stream.hostPhoto] : [],
    ageRange: '',
    area: '',
    distanceKm: null,
    interests: [],
    discoverableBy: 'everyone',
    wantsToDiscover: 'everyone',
    identity: 'woman',
    showIdentity: false,
    subscriptionTier: 'free',
  }

  return (
    <div className="animate-page-enter fixed inset-0 z-40 flex flex-col overflow-hidden bg-ink-900 text-white">
      {/* Stage */}
      <div className="absolute inset-0">
        {focusedTrack ? (
          <video ref={stageVideoRef} autoPlay playsInline className="size-full object-cover" />
        ) : (
          <div
            className="size-full scale-110 bg-cover bg-center blur-md"
            style={{ backgroundImage: `url(${focused?.photo ?? stream.hostPhoto})` }}
            aria-hidden="true"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-b from-black/50 via-transparent to-black/70" aria-hidden="true" />
      </div>

      {/* Top bar */}
      <div className="relative z-10 flex items-center gap-3 p-4">
        <img src={stream.hostPhoto} alt="" className="size-10 rounded-full border-2 border-white/70 object-cover" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-bold">{stream.title}</p>
          <p className="text-xs text-white/70">{stream.hostName} is live</p>
        </div>
        {isHost && (
          <button
            type="button"
            onClick={handleSwitchCamera}
            aria-label="Switch camera"
            className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
          >
            <RefreshCcw className="size-5" aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          onClick={handleLeave}
          disabled={ending}
          aria-label={isHost ? 'End stream' : 'Leave stream'}
          className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
        >
          <X className="size-5" aria-hidden="true" />
        </button>
      </div>

      {isHost && <JoinRequestPanel requests={joinRequests} onRespond={handleRespond} />}
      {focused && <ParticipantStack participants={participants} focusedId={focused.id} onFocus={setFocusedId} />}
      <div ref={remoteAudioRef} className="hidden" aria-hidden="true" />
      {mediaError && (
        <div role="alert" className="absolute left-1/2 top-1/2 z-20 flex max-w-sm -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-3 rounded-2xl bg-black/80 p-4 text-center text-sm">
          <span>{mediaError}</span>
          <button type="button" className="rounded-full bg-white/20 px-4 py-2 font-semibold" onClick={() => setRetryMedia((value) => value + 1)}>
            Reconnect media
          </button>
        </div>
      )}

      <div className="relative z-10 mt-auto flex flex-col gap-3 p-4">
        <ViewerStrip viewers={viewers} count={viewers.length} />

        <div className={cn(isHost && 'flex justify-center')}>
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            disabled={!canChat}
            placeholder={canChat ? 'Say something…' : `Join to chat (${previewSecondsLeft}s preview)`}
          />
        </div>

        {!isHost && canChat && (
          <div className="relative flex items-center gap-2">
            <button
              type="button"
              onClick={() => setGiftPickerOpen((v) => !v)}
              aria-label="Send a gift"
              className="flex size-10 cursor-pointer items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
            >
              <Gift className="size-5" aria-hidden="true" />
            </button>
            {giftPickerOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-56 rounded-2xl bg-white p-3 shadow-float">
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
            <button
              type="button"
              onClick={() => void handleRequestCall()}
              disabled={startingCall}
              aria-label="Request a video call"
              className="flex size-10 cursor-pointer items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
            >
              <PhoneCall className="size-5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={handleRequestJoinStream}
              aria-label="Ask to join the stream"
              className="flex size-10 cursor-pointer items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
            >
              <UserPlus className="size-5" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {showJoinGate && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-black/70 p-6 text-center">
          <p className="text-lg font-bold">Join to keep watching</p>
          <p className="max-w-xs text-sm text-white/80">Join to chat, send gifts, and request a video call with {stream.hostName}.</p>
          <button
            type="button"
            onClick={() => setJoinedToChat(true)}
            className="cursor-pointer rounded-full bg-primary-500 px-8 py-3 font-semibold text-white hover:bg-primary-600"
          >
            Join
          </button>
        </div>
      )}
      {activeCallId && (
        <CallScreen
          callId={activeCallId}
          profile={hostProfile}
          mode="video"
          onEnd={() => setActiveCallId(null)}
        />
      )}
    </div>
  )
}
