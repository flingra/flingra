import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronDown, LifeBuoy, LogOut, Settings, User } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { signOut } from '@/lib/api/auth'
import { useSessionStore } from '@/lib/stores/session-store'

export function AccountMenu({ name, photo }: { name: string; photo?: string }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const setSession = useSessionStore((state) => state.setSession)

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

  async function handleSignOut() {
    await signOut()
    setSession(null)
    setOpen(false)
    navigate('/login')
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex cursor-pointer items-center gap-2 rounded-full border border-ink-100 py-1 pl-1 pr-2.5 shadow-soft transition-shadow hover:shadow-float"
      >
        <Avatar name={name} src={photo} size="sm" />
        <ChevronDown className="size-4 text-ink-400" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-2 w-56 overflow-hidden rounded-2xl border border-ink-100 bg-white py-2 shadow-float"
        >
          <Link
            to="/settings/profile"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-3 px-4 py-2.5 text-sm text-ink-700 hover:bg-ink-50"
          >
            <User className="size-4" aria-hidden="true" /> My profile
          </Link>
          <Link
            to="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-3 px-4 py-2.5 text-sm text-ink-700 hover:bg-ink-50"
          >
            <Settings className="size-4" aria-hidden="true" /> Settings
          </Link>
          <Link
            to="/safety"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-3 px-4 py-2.5 text-sm text-ink-700 hover:bg-ink-50"
          >
            <LifeBuoy className="size-4" aria-hidden="true" /> Safety &amp; help
          </Link>
          <div className="my-1 border-t border-ink-100" />
          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            className="flex w-full cursor-pointer items-center gap-3 px-4 py-2.5 text-left text-sm text-danger hover:bg-danger/5"
          >
            <LogOut className="size-4" aria-hidden="true" /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}
