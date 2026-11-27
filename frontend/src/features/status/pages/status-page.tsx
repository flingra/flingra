import { type ChangeEvent, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { MemberAvatar } from '@/components/ui/member-avatar'
import { VideoThumbnail } from '@/components/ui/video-thumbnail'
import { VideoPlayerDialog } from '@/components/ui/video-player-dialog'
import { listNearbyStatuses, createStatus } from '@/lib/api/status'
import { listNearbyVideos } from '@/lib/api/profiles'
import { ApiError } from '@/lib/api/types'
import { StatusViewer } from '../components/status-viewer'
import { useSessionStore } from '@/lib/stores/session-store'

export function StatusPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const accountId = useSessionStore((state) => state.session?.accountId)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [viewerAuthorId, setViewerAuthorId] = useState<string | null>(null)
  const [playingVideo, setPlayingVideo] = useState<string | null>(null)

  const { data: statuses, isLoading, isError, refetch } = useQuery({ queryKey: ['statuses'], queryFn: listNearbyStatuses })
  const { data: nearbyVideos } = useQuery({ queryKey: ['nearby-videos'], queryFn: listNearbyVideos })

  const byAuthor = useMemo(() => {
    const groups = new Map<string, { authorId: string; authorName: string; authorPhoto: string; items: typeof statuses }>()
    for (const status of statuses ?? []) {
      const group = groups.get(status.authorId)
      if (group) group.items?.push(status)
      else groups.set(status.authorId, { authorId: status.authorId, authorName: status.authorName, authorPhoto: status.authorPhoto, items: [status] })
    }
    return Array.from(groups.values())
  }, [statuses])

  const myStatuses = byAuthor.find((group) => group.authorId === accountId)
  const otherStatuses = byAuthor.filter((group) => group.authorId !== accountId)
  const activeGroup = byAuthor.find((group) => group.authorId === viewerAuthorId)

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      await createStatus(file)
      await queryClient.invalidateQueries({ queryKey: ['statuses'] })
      showToast({ title: 'Status posted', variant: 'success' })
    } catch (error) {
      showToast({
        title: 'Could not post status',
        description: error instanceof ApiError ? error.message : 'Check your connection and try again.',
        variant: 'error',
      })
    } finally {
      setUploading(false)
    }
  }

  if (isLoading) return <PageSpinner label="Loading statuses" />
  if (isError) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12">
        <ErrorState title="Couldn't load statuses" action={{ label: 'Retry', onClick: () => refetch() }} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Status</h1>
      <p className="mt-1 text-sm text-ink-500">See what people near you are sharing. Video status is capped at 50 seconds.</p>

      <div className="mt-6 flex flex-col gap-2">
        <button
          type="button"
          onClick={() => (myStatuses ? setViewerAuthorId(accountId ?? null) : fileInputRef.current?.click())}
          className="flex w-full cursor-pointer items-center gap-3 rounded-2xl border border-ink-100 bg-white p-3 text-left shadow-soft transition-shadow hover:shadow-float"
        >
          <span className="relative">
            <img
              src={myStatuses?.authorPhoto ?? 'https://i.pravatar.cc/100?img=12'}
              alt=""
              className={`size-14 rounded-full object-cover ${myStatuses ? 'ring-2 ring-primary-500 ring-offset-2' : 'opacity-70'}`}
            />
            <span className="absolute -bottom-1 -right-1 flex size-6 items-center justify-center rounded-full bg-primary-500 text-white ring-2 ring-white">
              <Plus className="size-3.5" aria-hidden="true" />
            </span>
          </span>
          <div>
            <p className="font-semibold text-ink-900">Your status</p>
            <p className="text-sm text-ink-500">{uploading ? 'Uploading…' : myStatuses ? 'Tap to view' : 'Add a photo or video'}</p>
          </div>
        </button>
        <input ref={fileInputRef} type="file" accept="image/*,video/*" className="sr-only" onChange={handleUpload} disabled={uploading} />
      </div>

      {otherStatuses.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="No statuses nearby yet" description="When people near you share a status, it shows up here." />
        </div>
      ) : (
        <div className="mt-6">
          <p className="mb-2 text-sm font-medium text-ink-500">Near you</p>
          <div className="flex gap-4 overflow-x-auto pb-2">
            {otherStatuses.map((group) => (
              <button
                key={group.authorId}
                type="button"
                onClick={() => setViewerAuthorId(group.authorId)}
                className="flex shrink-0 cursor-pointer flex-col items-center gap-1.5"
              >
                <MemberAvatar id={group.authorId} name={group.authorName} photo={group.authorPhoto} size="lg" />
                <span className="max-w-16 truncate text-xs font-medium text-ink-700">{group.authorName}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {nearbyVideos && nearbyVideos.length > 0 && (
        <div className="mt-8">
          <p className="mb-2 text-sm font-medium text-ink-500">Videos near you</p>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {nearbyVideos.map((item) => (
              <div key={`${item.authorId}-${item.video}`}>
                <VideoThumbnail src={item.video} poster={item.authorPhoto} onClick={() => setPlayingVideo(item.video)} />
                <p className="mt-1 truncate text-xs font-medium text-ink-600">{item.authorName}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeGroup && activeGroup.items && (
        <StatusViewer statuses={activeGroup.items} startIndex={0} onClose={() => setViewerAuthorId(null)} />
      )}

      <VideoPlayerDialog src={playingVideo} onClose={() => setPlayingVideo(null)} />
    </div>
  )
}
