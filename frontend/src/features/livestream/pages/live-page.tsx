import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
  getLiveStream,
  listJoinRequests,
  listParticipants,
  listStreamMessages,
  listStreamViewers,
  PREVIEW_SECONDS,
  requestToJoin,
  respondToJoinRequest,
  sendStreamMessage,
  simulateIncomingGift,
  simulateIncomingMessage,
  simulateJoinRequest,
} from '@/lib/api/livestream'
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
  const [frontCamera, setFrontCamera] = useState(true)

  const { data: stream, isLoading, isError } = useQuery({
    queryKey: ['live-stream', streamId],
    queryFn: () => getLiveStream(streamId),
    refetchInterval: 2500,
    retry: false,
  })
  const isHost = stream?.hostId === session?.accountId

  const { data: participants = [] } = useQuery({
    queryKey: ['live-participants', streamId],
    queryFn: () => listParticipants(streamId),
    refetchInterval: 2500,
    enabled: Boolean(stream),
  })
  const { data: viewers = [] } = useQuery({
    queryKey: ['live-viewers', streamId],
    queryFn: () => listStreamViewers(streamId),
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

  // Count down the free preview for a viewer who hasn't joined the chat yet.
  useEffect(() => {
    if (isHost || joinedToChat || !stream) return
    if (previewSecondsLeft <= 0) return
    const timer = setInterval(() => setPreviewSecondsLeft((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(timer)
  }, [isHost, joinedToChat, stream, previewSecondsLeft])

  // Simulate another member chatting in, and (for the host) asking to join or
  // sending a gift, so the flows are testable without a second real account.
  const simulatedJoinRequestFired = useRef(false)
  useEffect(() => {
    if (!stream) return
    const chatTimer = setInterval(() => simulateIncomingMessage(stream.id), 6000)
    let giftTimer: ReturnType<typeof setInterval> | undefined
    let joinTimer: ReturnType<typeof setTimeout> | undefined
    if (isHost) {
      giftTimer = setInterval(() => {
        simulateIncomingGift(stream.id)
        queryClient.invalidateQueries({ queryKey: ['live-messages', streamId] })
        queryClient.invalidateQueries({ queryKey: ['received-gifts'] })
      }, 9000)
      if (!simulatedJoinRequestFired.current) {
        simulatedJoinRequestFired.current = true
        joinTimer = setTimeout(() => simulateJoinRequest(stream.id), 5000)
      }
    }
    return () => {
      clearInterval(chatTimer)
      if (giftTimer) clearInterval(giftTimer)
      if (joinTimer) clearTimeout(joinTimer)
    }
  }, [stream, isHost, streamId, queryClient])

  async function handleLeave() {
    if (isHost && stream) {
      setEnding(true)
      await endStream(stream.id)
    }
    navigate('/discover')
  }

  async function handleRespond(requestId: string, accept: boolean) {
    await respondToJoinRequest(requestId, accept)
    await queryClient.invalidateQueries({ queryKey: ['live-join-requests', streamId] })
    await queryClient.invalidateQueries({ queryKey: ['live-participants', streamId] })
  }

  async function handleSend(text: string) {
    await sendStreamMessage(streamId, text)
    await queryClient.invalidateQueries({ queryKey: ['live-messages', streamId] })
  }

  async function handleSendGift(giftTypeId: string) {
    setGiftPickerOpen(false)
    try {
      const gift = await spendOwnedGift(giftTypeId)
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
    await requestToJoin(streamId)
    showToast({ title: 'Request sent', description: 'The host will see your request to join.', variant: 'success' })
  }

  function handleRequestCall() {
    showToast({ title: 'Call request sent', description: `${stream?.hostName} will be notified.`, variant: 'success' })
  }

  function handleSwitchCamera() {
    setFrontCamera((current) => !current)
    showToast({ title: `Switched to ${frontCamera ? 'back' : 'front'} camera`, variant: 'info' })
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
  const canChat = isHost || joinedToChat

  return (
    <div className="animate-page-enter fixed inset-0 z-40 flex flex-col overflow-hidden bg-ink-900 text-white">
      {/* Stage */}
      <div className="absolute inset-0">
        {focused?.id === stream.hostId && stream.hostVideo ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video src={stream.hostVideo} autoPlay loop muted playsInline className="size-full object-cover" />
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

      <div className="relative z-10 mt-auto flex flex-col gap-3 p-4">
        <ViewerStrip viewers={viewers} count={viewers.length + 24} />

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
              onClick={handleRequestCall}
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
    </div>
  )
}
