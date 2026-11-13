import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useFocusTrap } from '@/lib/use-focus-trap'
import type { Status } from '@/lib/api/types'

const IMAGE_DURATION_MS = 5000

export function StatusViewer({
  statuses,
  startIndex,
  onClose,
}: {
  statuses: Status[]
  startIndex: number
  onClose: () => void
}) {
  const [index, setIndex] = useState(startIndex)
  const containerRef = useFocusTrap(true)
  const current = statuses[index]

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight') next()
      if (event.key === 'ArrowLeft') prev()
    }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index])

  useEffect(() => {
    if (!current || current.kind !== 'image') return
    const timer = setTimeout(next, IMAGE_DURATION_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index])

  function next() {
    if (index + 1 >= statuses.length) {
      onClose()
      return
    }
    setIndex(index + 1)
  }

  function prev() {
    setIndex((current) => Math.max(0, current - 1))
  }

  if (!current) return null

  return createPortal(
    <div ref={containerRef} role="dialog" aria-modal="true" aria-label={`${current.authorName}'s status`} className="fixed inset-0 z-50 bg-black">
      <div className="absolute inset-x-3 top-3 z-10 flex gap-1.5">
        {statuses.map((status, i) => (
          <div key={status.id} className="h-1 flex-1 overflow-hidden rounded-full bg-white/30">
            <div className={`h-full bg-white ${i < index ? 'w-full' : i === index ? 'w-full animate-pulse' : 'w-0'}`} />
          </div>
        ))}
      </div>

      <div className="absolute left-3 right-3 top-7 z-10 flex items-center gap-2.5">
        <img src={current.authorPhoto} alt="" className="size-9 rounded-full border-2 border-white object-cover" />
        <span className="font-semibold text-white drop-shadow-sm">{current.authorName}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-auto flex size-9 cursor-pointer items-center justify-center rounded-full text-white hover:bg-white/10"
        >
          <X className="size-5" aria-hidden="true" />
        </button>
      </div>

      <div className="flex size-full items-center justify-center">
        {current.kind === 'video' ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video src={current.media} autoPlay onEnded={next} className="max-h-full max-w-full" />
        ) : (
          <img src={current.media} alt="" className="max-h-full max-w-full object-contain" />
        )}
      </div>

      <button type="button" onClick={prev} aria-label="Previous status" className="absolute inset-y-0 left-0 w-1/3 cursor-pointer" />
      <button type="button" onClick={next} aria-label="Next status" className="absolute inset-y-0 right-0 w-1/3 cursor-pointer" />
    </div>,
    document.body,
  )
}
