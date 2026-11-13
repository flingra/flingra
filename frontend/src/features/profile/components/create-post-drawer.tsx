import { type ChangeEvent, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ImagePlus, Video as VideoIcon, X } from 'lucide-react'
import { Drawer } from '@/components/ui/drawer'
import { Field } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { Chip } from '@/components/ui/chip'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { uploadPhoto, uploadVideo } from '@/lib/api/profiles'
import { createPost } from '@/lib/api/posts'
import { ApiError } from '@/lib/api/types'

type Mode = 'photos' | 'video'

const MIN_PHOTOS = 3

export function CreatePostDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<Mode>('photos')
  const [photos, setPhotos] = useState<string[]>([])
  const [video, setVideo] = useState<string | null>(null)
  const [caption, setCaption] = useState('')
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canPost = photos.length >= MIN_PHOTOS || Boolean(video)

  function reset() {
    setPhotos([])
    setVideo(null)
    setCaption('')
    setError(null)
    setMode('photos')
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function handlePhotosChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length === 0) return
    setUploading(true)
    try {
      const urls = await Promise.all(files.map((file) => uploadPhoto(file)))
      setPhotos((current) => [...current, ...urls])
    } finally {
      setUploading(false)
    }
  }

  async function handleVideoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      setVideo(await uploadVideo(file))
    } finally {
      setUploading(false)
    }
  }

  async function handleSubmit() {
    setError(null)
    setSubmitting(true)
    try {
      await createPost({ photos, video: video ?? undefined, caption: caption || undefined })
      await queryClient.invalidateQueries({ queryKey: ['my-posts'] })
      showToast({ title: 'Posted', description: 'Your post is now visible on your profile.', variant: 'success' })
      handleClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create post. Check your connection and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer open={open} onClose={handleClose} title="Create post">
      <div className="flex flex-col gap-4">
        <div className="inline-flex w-fit gap-1 rounded-full bg-ink-100 p-1">
          <Chip type="button" selected={mode === 'photos'} onClick={() => setMode('photos')} className="border-0">
            <ImagePlus className="size-4" aria-hidden="true" /> Photos
          </Chip>
          <Chip type="button" selected={mode === 'video'} onClick={() => setMode('video')} className="border-0">
            <VideoIcon className="size-4" aria-hidden="true" /> Video
          </Chip>
        </div>

        {mode === 'photos' ? (
          <div>
            <div className="flex flex-wrap gap-3">
              {photos.map((photo, index) => (
                <div key={photo} className="relative size-20">
                  <img src={photo} alt="" className="size-full rounded-2xl object-cover" />
                  <button
                    type="button"
                    onClick={() => setPhotos((current) => current.filter((_, i) => i !== index))}
                    aria-label="Remove photo"
                    className="absolute -right-1.5 -top-1.5 cursor-pointer rounded-full bg-ink-900 p-1 text-white hover:bg-ink-700"
                  >
                    <X className="size-3" aria-hidden="true" />
                  </button>
                </div>
              ))}
              <label className="flex size-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-ink-200 text-ink-400 hover:border-ink-300">
                <ImagePlus className="size-5" aria-hidden="true" />
                <span className="text-xs">{uploading ? 'Uploading' : 'Add'}</span>
                <input type="file" accept="image/*" multiple className="sr-only" onChange={handlePhotosChange} disabled={uploading} />
              </label>
            </div>
            <p className="mt-2 text-xs text-ink-400">
              {photos.length}/{MIN_PHOTOS} minimum
            </p>
          </div>
        ) : (
          <div>
            {video ? (
              <div className="relative">
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video src={video} controls className="aspect-video w-full rounded-2xl bg-ink-900" />
                <button
                  type="button"
                  onClick={() => setVideo(null)}
                  aria-label="Remove video"
                  className="absolute -right-1.5 -top-1.5 cursor-pointer rounded-full bg-ink-900 p-1 text-white hover:bg-ink-700"
                >
                  <X className="size-3" aria-hidden="true" />
                </button>
              </div>
            ) : (
              <label className="flex aspect-video w-full cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed border-ink-200 text-ink-400 hover:border-ink-300">
                <VideoIcon className="size-6" aria-hidden="true" />
                <span className="text-xs">{uploading ? 'Uploading' : 'Add a video'}</span>
                <input type="file" accept="video/*" className="sr-only" onChange={handleVideoChange} disabled={uploading} />
              </label>
            )}
          </div>
        )}

        <Field id="post-caption" label="Caption" optional hint={`${caption.length}/280`}>
          <Textarea
            id="post-caption"
            maxLength={280}
            value={caption}
            onChange={(event) => setCaption(event.target.value)}
            placeholder="Say something about this post"
          />
        </Field>

        {error && (
          <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
            {error}
          </p>
        )}

        <Button onClick={handleSubmit} loading={submitting} disabled={!canPost || uploading}>
          Post
        </Button>
      </div>
    </Drawer>
  )
}
