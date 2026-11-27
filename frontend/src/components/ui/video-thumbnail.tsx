import { useEffect, useRef, useState } from 'react'
import { Play } from 'lucide-react'

export async function createBlurredVideoPreview(file: File): Promise<string> {
  const source = URL.createObjectURL(file)
  const video = document.createElement('video')
  video.muted = true
  video.preload = 'auto'
  video.src = source

  try {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => reject(new Error('Video preview generation timed out.')), 10_000)
      video.addEventListener('loadeddata', () => {
        window.clearTimeout(timeout)
        resolve()
      }, { once: true })
      video.addEventListener('error', () => {
        window.clearTimeout(timeout)
        reject(new Error('Could not read the video to create a preview.'))
      }, { once: true })
      video.load()
    })

    if (!video.videoWidth || !video.videoHeight) {
      throw new Error('The video has no previewable frame.')
    }

    const canvas = document.createElement('canvas')
    canvas.width = 160
    canvas.height = 160
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Could not create a video preview.')

    const cropSize = Math.min(video.videoWidth, video.videoHeight)
    context.filter = 'blur(16px)'
    context.drawImage(
      video,
      (video.videoWidth - cropSize) / 2,
      (video.videoHeight - cropSize) / 2,
      cropSize,
      cropSize,
      0,
      0,
      canvas.width,
      canvas.height,
    )

    const preview = canvas.toDataURL('image/jpeg', 0.35)
    if (preview.length > 24_000) throw new Error('The generated video preview is too large.')
    return preview
  } finally {
    video.removeAttribute('src')
    video.load()
    URL.revokeObjectURL(source)
  }
}

/**
 * A video tile that auto-captures a frame as its thumbnail instead of showing a
 * blank box — or, if `poster` is given (e.g. the author's profile photo), uses
 * that instead and skips frame capture entirely.
 */
export function VideoThumbnail({ src, poster, onClick }: { src: string; poster?: string; onClick: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [thumbnail, setThumbnail] = useState<string | null>(null)

  useEffect(() => {
    if (poster) return
    setThumbnail(null)
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return

    function seekToFrame() {
      if (!video) return
      video.currentTime = Math.min(1, (video.duration || 2) / 4)
    }

    function draw() {
      if (!video || !canvas) return
      try {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        const ctx = canvas.getContext('2d')
        ctx?.drawImage(video, 0, 0)
        setThumbnail(canvas.toDataURL('image/jpeg'))
      } catch {
        // Cross-origin frame can't always be read back into a canvas; the play
        // overlay on a plain dark tile still communicates "this is a video".
      }
    }

    video.addEventListener('loadedmetadata', seekToFrame)
    video.addEventListener('seeked', draw)
    return () => {
      video.removeEventListener('loadedmetadata', seekToFrame)
      video.removeEventListener('seeked', draw)
    }
  }, [src, poster])

  return (
    <button type="button" onClick={onClick} className="group relative block aspect-square w-full cursor-pointer overflow-hidden rounded-2xl bg-ink-800">
      {!poster && (
        <>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={videoRef} src={src} muted playsInline preload="metadata" crossOrigin="anonymous" className="sr-only" />
          <canvas ref={canvasRef} className="hidden" />
        </>
      )}
      {(poster ?? thumbnail) && <img src={poster ?? thumbnail ?? undefined} alt="" className="size-full object-cover" />}
      <span className="absolute inset-0 flex items-center justify-center bg-black/25 transition-colors group-hover:bg-black/35">
        <span className="flex size-10 items-center justify-center rounded-full bg-white/95 text-ink-900 shadow-soft">
          <Play className="ml-0.5 size-4 fill-current" aria-hidden="true" />
        </span>
      </span>
    </button>
  )
}
