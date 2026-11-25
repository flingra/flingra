import { useEffect, useRef, useState } from 'react'
import { Bell, Gift, ShieldCheck, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Drawer } from '@/components/ui/drawer'
import { useToast } from '@/components/ui/toast'
import { apiWebSocketUrl } from '@/lib/api/client'
import { useSessionStore } from '@/lib/stores/session-store'

const NOTIFICATIONS = [
  { id: 'welcome', icon: Sparkles, title: 'Welcome to Flingra', body: 'Finish your profile to start appearing in Discover.' },
  { id: 'approved', icon: ShieldCheck, title: 'Profile approved', body: 'Your profile passed review and is now visible to others.' },
]

type RealtimeEvent = {
  id?: unknown
  type?: unknown
  data?: {
    giftEmoji?: unknown
    giftId?: unknown
    giftName?: unknown
    senderName?: unknown
  }
}

type NotificationItem = {
  id: string
  icon: LucideIcon
  title: string
  body: string
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [notifications, setNotifications] = useState<NotificationItem[]>(NOTIFICATIONS)
  const containerRef = useRef<HTMLDivElement>(null)
  const accountId = useSessionStore((state) => state.session?.stage === 'active' ? state.session.accountId : null)
  const { showToast } = useToast()

  useEffect(() => {
    setNotifications(NOTIFICATIONS)
    setUnreadCount(0)
    if (!accountId) return

    let socket: WebSocket | null = null
    let retryTimer: number | undefined
    let retryDelay = 1000
    let cursor: number | null = null
    let disposed = false

    function connect() {
      const socketUrl = apiWebSocketUrl('/realtime/ws')
      if (!socketUrl || disposed) return

      const url = new URL(socketUrl)
      if (cursor !== null) url.searchParams.set('after', String(cursor))
      const connection = new WebSocket(url)
      socket = connection
      connection.addEventListener('open', () => {
        retryDelay = 1000
      })
      connection.addEventListener('message', (message) => {
        let event: RealtimeEvent
        try {
          event = JSON.parse(message.data) as RealtimeEvent
        } catch {
          return
        }

        if (typeof event.id === 'number' && Number.isSafeInteger(event.id)) cursor = event.id
        if (
          event.type !== 'wallet.gift_received'
          || typeof event.id !== 'number'
          || typeof event.data?.giftId !== 'string'
          || typeof event.data.giftName !== 'string'
          || typeof event.data.giftEmoji !== 'string'
          || typeof event.data.senderName !== 'string'
        ) return

        const notification = {
          id: `gift-${event.id}`,
          icon: Gift,
          title: 'Gift received',
          body: `${event.data.senderName} sent you ${event.data.giftEmoji} ${event.data.giftName}.`,
        }
        setNotifications((current) => [notification, ...current].slice(0, 20))
        setUnreadCount((current) => current + 1)
        showToast({
          title: notification.title,
          description: `${notification.body} Redeem it from your wallet.`,
          variant: 'success',
        })
      })
      connection.addEventListener('close', () => {
        if (disposed) return
        retryTimer = window.setTimeout(connect, retryDelay)
        retryDelay = Math.min(retryDelay * 2, 30_000)
      })
      connection.addEventListener('error', () => connection.close())
    }

    connect()
    return () => {
      disposed = true
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [accountId, showToast])

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 639px)')
    const updateViewport = () => setIsMobile(mediaQuery.matches)
    updateViewport()
    mediaQuery.addEventListener('change', updateViewport)
    return () => mediaQuery.removeEventListener('change', updateViewport)
  }, [])

  useEffect(() => {
    if (!open || isMobile) return
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
  }, [open, isMobile])

  const notificationItems = notifications.map(({ id, icon: Icon, title, body }) => (
    <div
      key={id}
      role={isMobile ? undefined : 'menuitem'}
      className="flex items-start gap-3 px-4 py-3 hover:bg-ink-50"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-semibold text-ink-900">{title}</p>
        <p className="text-xs text-ink-500">{body}</p>
      </div>
    </div>
  ))

  return (
    <>
      <div className="relative" ref={containerRef}>
        <button
          type="button"
          onClick={() => {
            setOpen((current) => !current)
            setUnreadCount(0)
          }}
          aria-haspopup={isMobile ? 'dialog' : 'menu'}
          aria-expanded={open}
          aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
          className="relative flex size-10 cursor-pointer items-center justify-center rounded-full border border-ink-100 text-ink-700 shadow-soft transition-shadow hover:shadow-float"
        >
          <Bell className="size-4.5" aria-hidden="true" />
          {unreadCount > 0 && <span className="absolute right-2 top-2 size-2 rounded-full bg-primary-500" aria-hidden="true" />}
        </button>
        {open && !isMobile && (
          <div
            role="menu"
            className="fixed inset-x-4 top-[4.25rem] z-40 overflow-hidden rounded-2xl border border-ink-100 bg-white py-2 shadow-float sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-72"
          >
            <p className="px-4 py-2 text-sm font-bold text-ink-900">Notifications</p>
            {notificationItems}
          </div>
        )}
      </div>
      {open && isMobile && (
        <Drawer open onClose={() => setOpen(false)} title="Notifications">
          <div className="-mx-4 -mt-2 divide-y divide-ink-100">{notificationItems}</div>
        </Drawer>
      )}
    </>
  )
}
