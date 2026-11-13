import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Flag,
  MapPin,
  MessageCircle,
  ShieldOff,
  Heart,
  ShieldCheck,
  Phone,
  Radio,
  Video as VideoIcon,
  Lock,
  HeartHandshake,
} from 'lucide-react'
import { getPresence } from '@/lib/api/presence'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PageSpinner } from '@/components/ui/spinner'
import { ErrorState } from '@/components/ui/state-message'
import { getOwnProfile, getProfile } from '@/lib/api/profiles'
import { blockMember } from '@/lib/api/safety'
import { getOrCreateThread } from '@/lib/api/chat'
import { isVideoUnlocked, sendMeetupPayment, unlockVideo } from '@/lib/api/wallet'
import { ApiError, type ProfileVideo } from '@/lib/api/types'
import { useToast } from '@/components/ui/toast'
import { cn, formatNaira } from '@/lib/utils'
import { ReportDialog } from '@/features/safety/components/report-dialog'
import { CallScreen } from '@/features/calls/components/call-screen'
import { VideoThumbnail } from '@/components/ui/video-thumbnail'
import { VideoPlayerDialog } from '@/components/ui/video-player-dialog'
import { ChatDrawer } from '../components/chat-drawer'

export function ProfileDetailPage() {
  const { profileId = '' } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [reportOpen, setReportOpen] = useState(false)
  const [blockConfirmOpen, setBlockConfirmOpen] = useState(false)
  const [blocking, setBlocking] = useState(false)
  const [interested, setInterested] = useState(false)
  const [notified, setNotified] = useState(false)
  const [chatThreadId, setChatThreadId] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [activePhoto, setActivePhoto] = useState(0)
  const [callMode, setCallMode] = useState<'video' | 'voice' | null>(null)
  const [playingVideo, setPlayingVideo] = useState<string | null>(null)
  const [unlockTarget, setUnlockTarget] = useState<ProfileVideo | null>(null)
  const [unlocking, setUnlocking] = useState(false)
  const [paymentOpen, setPaymentOpen] = useState(false)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [sendingPayment, setSendingPayment] = useState(false)
  const [paymentError, setPaymentError] = useState<string | null>(null)

  const { data: profile, isLoading, isError, refetch } = useQuery({
    queryKey: ['profile', profileId],
    queryFn: () => getProfile(profileId),
  })
  const { data: ownProfile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, retry: false })

  async function handleUnlockVideo() {
    if (!unlockTarget?.priceNaira || !profile) return
    setUnlocking(true)
    try {
      await unlockVideo(unlockTarget.url, unlockTarget.priceNaira, profile.displayName)
      await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
      showToast({ title: 'Video unlocked', variant: 'success' })
      setPlayingVideo(unlockTarget.url)
      setUnlockTarget(null)
    } catch (error) {
      showToast({
        title: 'Could not unlock video',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setUnlocking(false)
    }
  }

  async function handleSendPayment() {
    if (!profile) return
    setPaymentError(null)
    setSendingPayment(true)
    try {
      await sendMeetupPayment(profile.id, profile.displayName, Number(paymentAmount))
      await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
      await queryClient.invalidateQueries({ queryKey: ['meetup-payments'] })
      showToast({
        title: 'Payment held',
        description: `${formatNaira(Number(paymentAmount))} will release once you confirm you met up.`,
        variant: 'success',
      })
      setPaymentOpen(false)
      setPaymentAmount('')
    } catch (error) {
      setPaymentError(error instanceof ApiError ? error.message : 'Could not send payment. Try again.')
    } finally {
      setSendingPayment(false)
    }
  }

  async function handleShowInterest() {
    if (!profile) return
    setInterested(true)
    showToast({ title: 'Interest sent', description: `${profile.displayName} will be notified.`, variant: 'success' })
    const thread = await getOrCreateThread(profile.id, profile.displayName, profile.photos[0])
    setChatThreadId(thread.id)
    setTimeout(() => {
      setNotified(true)
      showToast({ title: `${profile.displayName} was notified`, description: 'You can now chat with each other.', variant: 'info' })
    }, 1200)
  }

  async function handleBlock() {
    setBlocking(true)
    try {
      await blockMember(profileId)
      showToast({ title: `${profile?.displayName ?? 'Member'} blocked`, description: 'They can no longer see your profile or contact you.', variant: 'success' })
      setBlockConfirmOpen(false)
      navigate('/discover')
    } finally {
      setBlocking(false)
    }
  }

  if (isLoading) return <PageSpinner label="Loading profile" />
  if (isError || !profile) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12">
        <ErrorState
          title="Profile unavailable"
          description="This profile may have been removed or is no longer available."
          action={{ label: 'Try again', onClick: () => refetch() }}
        />
      </div>
    )
  }

  const photos = profile.photos.length > 0 ? profile.photos : undefined
  const { isLive, streamId } = getPresence(profile.id)

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <Link to="/discover" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-ink-900">
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to Discover
      </Link>

      {isLive && streamId && (
        <Link
          to={`/live/${streamId}`}
          className="mt-4 flex items-center gap-3 rounded-2xl bg-danger px-4 py-3 text-white shadow-soft transition-opacity hover:opacity-90"
        >
          <Radio className="size-5 shrink-0" aria-hidden="true" />
          <span className="flex-1 text-sm font-semibold">{profile.displayName} is live right now</span>
          <span className="rounded-full bg-white/20 px-3 py-1 text-xs font-bold">Watch</span>
        </Link>
      )}

      <div className="mt-4 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
        <div className="relative aspect-square w-full overflow-hidden bg-primary-50 sm:aspect-[4/3]">
          {photos ? (
            <img src={photos[activePhoto]} alt={`${profile.displayName}'s photo`} className="size-full object-cover" />
          ) : (
            <div className="flex size-full items-center justify-center text-6xl font-bold text-primary-300">
              {profile.displayName[0]}
            </div>
          )}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/50 to-transparent" />
          <span className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-ink-900 shadow-soft">
            <ShieldCheck className="size-3.5 text-success" aria-hidden="true" /> Verified profile
          </span>
          <div className="absolute bottom-4 left-4 right-4 text-white">
            <h1 className="text-2xl font-bold drop-shadow-sm">
              {profile.displayName}, {profile.ageRange}
            </h1>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-white/90 drop-shadow-sm">
              <MapPin className="size-4" aria-hidden="true" /> {profile.area}
            </p>
          </div>
        </div>

        {photos && photos.length > 1 && (
          <div className="flex gap-2 overflow-x-auto border-b border-ink-100 p-3">
            {photos.map((photo, index) => (
              <button
                key={photo}
                type="button"
                onClick={() => setActivePhoto(index)}
                aria-label={`Show photo ${index + 1} of ${photos.length}`}
                aria-pressed={index === activePhoto}
                className={cn(
                  'size-16 shrink-0 overflow-hidden rounded-2xl ring-2 transition-opacity',
                  index === activePhoto ? 'ring-primary-500' : 'opacity-70 ring-transparent hover:opacity-100',
                )}
              >
                <img src={photo} alt="" className="size-full object-cover" />
              </button>
            ))}
          </div>
        )}

        <div className="p-6">
          {profile.showIdentity && profile.identity !== 'private' && (
            <Badge variant="neutral" className="mb-3 capitalize">
              {profile.identity}
            </Badge>
          )}
          <p className="text-ink-700">{profile.bio}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {profile.interests.map((interest) => (
              <Badge key={interest} variant="accent">
                {interest}
              </Badge>
            ))}
          </div>

          {profile.videos && profile.videos.length > 0 && (
            <div className="mt-5">
              <p className="mb-2 text-sm font-medium text-ink-800">Videos</p>
              <div className="grid max-w-xs grid-cols-3 gap-2">
                {profile.videos.map((video) => {
                  const locked = video.locked && !isVideoUnlocked(video.url)
                  return locked ? (
                    <button
                      key={video.url}
                      type="button"
                      onClick={() => setUnlockTarget(video)}
                      className="group relative flex aspect-square w-full cursor-pointer flex-col items-center justify-center gap-1 overflow-hidden rounded-2xl bg-ink-800 text-white"
                    >
                      <Lock className="size-5" aria-hidden="true" />
                      <span className="text-xs font-semibold">{formatNaira(video.priceNaira ?? 0)}</span>
                    </button>
                  ) : (
                    <VideoThumbnail key={video.url} src={video.url} onClick={() => setPlayingVideo(video.url)} />
                  )
                })}
              </div>
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            <Button
              variant={interested ? 'secondary' : 'accent'}
              onClick={handleShowInterest}
              disabled={interested}
            >
              <Heart className="size-4" aria-hidden="true" /> {interested ? 'Interest sent' : 'Show interest'}
            </Button>
            {notified && chatThreadId && (
              <Button variant="accent" onClick={() => setChatOpen(true)}>
                <MessageCircle className="size-4" aria-hidden="true" /> Chat
              </Button>
            )}
            {ownProfile?.identity === 'man' && profile.identity === 'woman' && (
              <Button variant="outline" onClick={() => setPaymentOpen(true)}>
                <HeartHandshake className="size-4" aria-hidden="true" /> Send meetup payment
              </Button>
            )}
            <Button variant="outline" onClick={() => setCallMode('voice')}>
              <Phone className="size-4" aria-hidden="true" /> Voice call
            </Button>
            <Button variant="outline" onClick={() => setCallMode('video')}>
              <VideoIcon className="size-4" aria-hidden="true" /> Video call
            </Button>
            <Button variant="outline" onClick={() => setReportOpen(true)}>
              <Flag className="size-4" aria-hidden="true" /> Report
            </Button>
            <Button variant="ghost" className="text-danger hover:bg-danger/5" onClick={() => setBlockConfirmOpen(true)}>
              <ShieldOff className="size-4" aria-hidden="true" /> Block
            </Button>
          </div>
        </div>
      </div>

      <ReportDialog open={reportOpen} onClose={() => setReportOpen(false)} targetId={profile.id} targetName={profile.displayName} onBlocked={() => navigate('/discover')} />

      <Dialog
        open={blockConfirmOpen}
        onClose={() => setBlockConfirmOpen(false)}
        title={`Block ${profile.displayName}?`}
        description="They won't be able to see your profile, discover you, or contact you. This also files a report with our safety team for review — repeat or serious reports can lead to a ban. You can unblock them later from Settings."
      >
        <div className="flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={() => setBlockConfirmOpen(false)}>
            Cancel
          </Button>
          <Button variant="destructive" className="flex-1" loading={blocking} onClick={handleBlock}>
            Block
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={!!unlockTarget}
        onClose={() => setUnlockTarget(null)}
        title="Unlock this video?"
        description={`Pay ${formatNaira(unlockTarget?.priceNaira ?? 0)} to watch this video. This is a demo charge — no real payment is made.`}
      >
        <div className="flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={() => setUnlockTarget(null)}>
            Cancel
          </Button>
          <Button className="flex-1" loading={unlocking} onClick={handleUnlockVideo}>
            Pay &amp; unlock
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={paymentOpen}
        onClose={() => setPaymentOpen(false)}
        title={`Send a payment to ${profile.displayName}`}
        description="Funds stay held until you confirm the meetup happened, then they release to her wallet."
      >
        <div className="flex flex-col gap-4">
          {paymentError && (
            <p role="alert" className="text-sm font-medium text-danger">
              {paymentError}
            </p>
          )}
          <Field id="payment-amount" label="Amount (₦)">
            <Input
              id="payment-amount"
              type="number"
              min={100}
              value={paymentAmount}
              onChange={(event) => setPaymentAmount(event.target.value)}
            />
          </Field>
          <Button loading={sendingPayment} disabled={!paymentAmount || Number(paymentAmount) <= 0} onClick={handleSendPayment}>
            Hold payment
          </Button>
        </div>
      </Dialog>

      {callMode && <CallScreen profile={profile} mode={callMode} onEnd={() => setCallMode(null)} />}
      <VideoPlayerDialog src={playingVideo} onClose={() => setPlayingVideo(null)} />
      {chatThreadId && (
        <ChatDrawer
          open={chatOpen}
          onClose={() => setChatOpen(false)}
          threadId={chatThreadId}
          otherId={profile.id}
          otherName={profile.displayName}
          otherPhoto={profile.photos[0]}
        />
      )}
    </div>
  )
}
