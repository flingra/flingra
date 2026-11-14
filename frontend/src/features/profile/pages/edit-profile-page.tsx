import { type ChangeEvent, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Images, Lock, Unlock, Video as VideoIcon, X } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/toast'
import { VideoThumbnail } from '@/components/ui/video-thumbnail'
import { VideoPlayerDialog } from '@/components/ui/video-player-dialog'
import { getOwnProfile, saveOwnProfile, uploadPhoto, uploadVideo } from '@/lib/api/profiles'
import { listMyPosts } from '@/lib/api/posts'
import type { ProfileVideo } from '@/lib/api/types'

export function EditProfilePage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile })
  const { data: myPosts } = useQuery({ queryKey: ['my-posts'], queryFn: listMyPosts })

  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [photos, setPhotos] = useState<string[]>([])
  const [videos, setVideos] = useState<ProfileVideo[]>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadingVideo, setUploadingVideo] = useState(false)
  const [playingVideo, setPlayingVideo] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    setDisplayName(data.displayName)
    setBio(data.bio)
    setPhotos(data.photos)
    setVideos(data.videos ?? [])
    setDirty(false)
  }, [data])

  async function handleAddPhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const url = await uploadPhoto(file)
      setPhotos((current) => [...current, url])
      setDirty(true)
    } finally {
      setUploading(false)
    }
  }

  function removePhoto(index: number) {
    setPhotos((current) => current.filter((_, i) => i !== index))
    setDirty(true)
  }

  async function handleAddVideo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploadingVideo(true)
    try {
      const url = await uploadVideo(file)
      setVideos((current) => [...current, { url }])
      setDirty(true)
    } finally {
      setUploadingVideo(false)
    }
  }

  function removeVideo(index: number) {
    setVideos((current) => current.filter((_, i) => i !== index))
    setDirty(true)
  }

  function toggleVideoLock(index: number) {
    setVideos((current) =>
      current.map((video, i) => (i === index ? { ...video, locked: !video.locked, priceNaira: video.locked ? undefined : video.priceNaira ?? 1000 } : video)),
    )
    setDirty(true)
  }

  function setVideoPrice(index: number, priceNaira: number) {
    setVideos((current) => current.map((video, i) => (i === index ? { ...video, priceNaira } : video)))
    setDirty(true)
  }

  function handleCancel() {
    if (!data) return
    setDisplayName(data.displayName)
    setBio(data.bio)
    setPhotos(data.photos)
    setVideos(data.videos ?? [])
    setDirty(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await saveOwnProfile({ displayName, bio, photos, videos })
      await queryClient.invalidateQueries({ queryKey: ['own-profile'] })
      setDirty(false)
      showToast({ title: 'Profile saved', variant: 'success' })
    } catch {
      showToast({ title: 'Could not save profile', description: 'Check your connection and try again.', variant: 'error' })
    } finally {
      setSaving(false)
    }
  }

  if (isLoading) return <PageSpinner label="Loading your profile" />
  if (isError) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12">
        <ErrorState title="Couldn't load your profile" action={{ label: 'Retry', onClick: () => refetch() }} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">My profile</h1>
      {data?.moderationStatus === 'pending' && (
        <p className="mt-2 inline-block rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">
          Pending review: not yet visible to other members
        </p>
      )}

      <Card className="mt-6">
        <div className="flex flex-col gap-5">
          <div>
            <p className="mb-2 text-sm font-medium text-ink-800">Photos</p>
            <div className="flex flex-wrap gap-3">
              {photos.map((photo, index) => (
                <div key={photo} className="relative size-20">
                  <img src={photo} alt="" className="size-full rounded-2xl object-cover" />
                  <button
                    type="button"
                    onClick={() => removePhoto(index)}
                    aria-label="Remove photo"
                    className="absolute -right-1.5 -top-1.5 cursor-pointer rounded-full bg-ink-900 p-1 text-white hover:bg-ink-700"
                  >
                    <X className="size-3" aria-hidden="true" />
                  </button>
                </div>
              ))}
              <label className="flex size-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-ink-200 text-ink-400 hover:border-ink-300">
                <Camera className="size-5" aria-hidden="true" />
                <span className="text-xs">{uploading ? 'Uploading' : 'Add'}</span>
                <input type="file" accept="image/*" className="sr-only" onChange={handleAddPhoto} disabled={uploading} />
              </label>
            </div>
          </div>

          <div>
            <p className="mb-2 text-sm font-medium text-ink-800">Videos</p>
            {data?.identity === 'woman' && (
              <p className="mb-3 text-xs text-ink-400">Lock a video and set a price — viewers pay to unlock it.</p>
            )}
            <div className={data?.identity === 'woman' ? 'grid grid-cols-2 gap-3 sm:grid-cols-3' : 'flex flex-wrap gap-3'}>
              {videos.map((video, index) =>
                data?.identity === 'woman' ? (
                  <div key={video.url} className="rounded-2xl border border-ink-100 p-2">
                    <div className="relative aspect-square w-full">
                      <VideoThumbnail src={video.url} onClick={() => setPlayingVideo(video.url)} />
                      <button
                        type="button"
                        onClick={() => removeVideo(index)}
                        aria-label="Remove video"
                        className="absolute -right-1.5 -top-1.5 cursor-pointer rounded-full bg-ink-900 p-1 text-white hover:bg-ink-700"
                      >
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleVideoLock(index)}
                      className="mt-2 flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-full border border-ink-200 py-1.5 text-xs font-semibold text-ink-700 hover:bg-ink-50"
                    >
                      {video.locked ? <Lock className="size-3" aria-hidden="true" /> : <Unlock className="size-3" aria-hidden="true" />}
                      {video.locked ? 'Locked' : 'Free to view'}
                    </button>
                    {video.locked && (
                      <input
                        type="number"
                        min={100}
                        value={video.priceNaira ?? ''}
                        onChange={(event) => setVideoPrice(index, Number(event.target.value))}
                        aria-label="Price in Naira"
                        placeholder="Price (₦)"
                        className="mt-2 w-full rounded-full border border-ink-200 px-3 py-1.5 text-center text-xs"
                      />
                    )}
                  </div>
                ) : (
                  <div key={video.url} className="relative size-20">
                    <VideoThumbnail src={video.url} onClick={() => setPlayingVideo(video.url)} />
                    <button
                      type="button"
                      onClick={() => removeVideo(index)}
                      aria-label="Remove video"
                      className="absolute -right-1.5 -top-1.5 cursor-pointer rounded-full bg-ink-900 p-1 text-white hover:bg-ink-700"
                    >
                      <X className="size-3" aria-hidden="true" />
                    </button>
                  </div>
                ),
              )}
              <label className="flex size-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-ink-200 text-ink-400 hover:border-ink-300">
                <VideoIcon className="size-5" aria-hidden="true" />
                <span className="text-xs">{uploadingVideo ? 'Uploading' : 'Add'}</span>
                <input type="file" accept="video/*" className="sr-only" onChange={handleAddVideo} disabled={uploadingVideo} />
              </label>
            </div>
          </div>

          <Field id="displayName" label="Display name">
            <Input
              id="displayName"
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value)
                setDirty(true)
              }}
            />
          </Field>

          <Field id="bio" label="Bio" optional hint={`${bio.length}/280`}>
            <Textarea
              id="bio"
              maxLength={280}
              value={bio}
              onChange={(event) => {
                setBio(event.target.value)
                setDirty(true)
              }}
            />
          </Field>

          {data && data.interests.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium text-ink-800">Interests</p>
              <div className="flex flex-wrap gap-2">
                {data.interests.map((interest) => (
                  <Badge key={interest}>{interest}</Badge>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={handleCancel} disabled={!dirty}>
              Cancel
            </Button>
            <Button className="flex-1" onClick={handleSave} loading={saving} disabled={!dirty}>
              Save
            </Button>
          </div>
        </div>
      </Card>

      <div className="mt-8">
        <h2 className="text-lg font-bold text-ink-900">My posts</h2>
        {myPosts && myPosts.length === 0 && (
          <div className="mt-3">
            <EmptyState
              title="No posts yet"
              description="Use the create button to share at least 3 photos or a video."
            />
          </div>
        )}
        {myPosts && myPosts.length > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2">
            {myPosts.map((post) => (
              <div key={post.id} className="relative aspect-square overflow-hidden rounded-2xl bg-ink-100">
                {post.video ? (
                  <>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <video src={post.video} className="size-full object-cover" muted />
                    <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full bg-black/60 text-white">
                      <VideoIcon className="size-3.5" aria-hidden="true" />
                    </span>
                  </>
                ) : (
                  <>
                    <img src={post.photos[0]} alt="" className="size-full object-cover" />
                    {post.photos.length > 1 && (
                      <span className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-xs font-medium text-white">
                        <Images className="size-3" aria-hidden="true" /> {post.photos.length}
                      </span>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <VideoPlayerDialog src={playingVideo} onClose={() => setPlayingVideo(null)} />
    </div>
  )
}
