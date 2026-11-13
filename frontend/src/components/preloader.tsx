import { useEffect, useState } from 'react'
import { Logo } from './logo'
import { cn } from '@/lib/utils'

/** Full-screen brand splash shown for a beat on first load, then fades out and unmounts. */
export function Preloader() {
  const [fading, setFading] = useState(false)
  const [mounted, setMounted] = useState(true)

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFading(true), 650)
    const unmountTimer = setTimeout(() => setMounted(false), 950)
    return () => {
      clearTimeout(fadeTimer)
      clearTimeout(unmountTimer)
    }
  }, [])

  if (!mounted) return null

  return (
    <div
      className={cn(
        'fixed inset-0 z-[100] flex items-center justify-center bg-ink-50 transition-opacity duration-300',
        fading ? 'pointer-events-none opacity-0' : 'opacity-100',
      )}
      aria-hidden="true"
    >
      <div className="relative flex size-20 items-center justify-center">
        <span className="absolute inset-0 animate-ping rounded-full bg-primary-500/25" />
        <span className="absolute inset-2 animate-pulse rounded-full bg-primary-500/15" />
        <Logo mark className="relative z-10 scale-150" />
      </div>
    </div>
  )
}
