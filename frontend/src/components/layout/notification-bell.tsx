import { useEffect, useRef, useState } from 'react'
import { Bell, ShieldCheck, Sparkles } from 'lucide-react'

const NOTIFICATIONS = [
  { id: 'welcome', icon: Sparkles, title: 'Welcome to Flingra', body: 'Finish your profile to start appearing in Discover.' },
  { id: 'approved', icon: ShieldCheck, title: 'Profile approved', body: 'Your profile passed review and is now visible to others.' },
]

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Notifications"
        className="relative flex size-10 cursor-pointer items-center justify-center rounded-full border border-ink-100 text-ink-700 shadow-soft transition-shadow hover:shadow-float"
      >
        <Bell className="size-4.5" aria-hidden="true" />
        <span className="absolute right-2 top-2 size-2 rounded-full bg-primary-500" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          className="fixed inset-x-4 top-[4.25rem] z-40 overflow-hidden rounded-2xl border border-ink-100 bg-white py-2 shadow-float sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-72"
        >
          <p className="px-4 py-2 text-sm font-bold text-ink-900">Notifications</p>
          {NOTIFICATIONS.map(({ id, icon: Icon, title, body }) => (
            <div key={id} role="menuitem" className="flex items-start gap-3 px-4 py-2.5 hover:bg-ink-50">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-ink-900">{title}</p>
                <p className="text-xs text-ink-500">{body}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
