import { useEffect, useRef, useState } from 'react'
import { Bell, Gift, HeartHandshake, MessageCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Drawer } from '@/components/ui/drawer'
import { useToast } from '@/components/ui/toast'
import { listRealtimeEvents } from '@/lib/api/realtime'
import { useSessionStore } from '@/lib/stores/session-store'

type NotificationItem = {
  id: string
  icon: LucideIcon
  title: string
  body: string
  href?: string
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const containerRef = useRef<HTMLDivElement>(null)
  const accountId = useSessionStore((state) => state.session?.stage === 'active' ? state.session.accountId : null)
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  useEffect(() => {
    setNotifications([])
    setUnreadCount(0)
    if (!accountId) return

    let pollTimer: number | undefined
    let retryDelay = 5000
    let cursor: number | undefined
    let disposed = false
    let reportedFailure = false

    async function poll() {
      try {
        const batch = await listRealtimeEvents(cursor)
        const isInitialCursor = cursor === undefined
        cursor = batch.cursor
        retryDelay = 5000
        reportedFailure = false
        if (!isInitialCursor) {
          for (const event of batch.events) {
            let notification: NotificationItem | null = null
            if (
              event.type === 'wallet.gift_received'
              && typeof event.data.giftId === 'string'
              && typeof event.data.giftName === 'string'
              && typeof event.data.giftEmoji === 'string'
              && typeof event.data.senderName === 'string'
            ) {
              notification = {
                id: `gift-${event.id}`,
                icon: Gift,
                title: 'Gift received',
                body: `${event.data.senderName} sent you ${event.data.giftEmoji} ${event.data.giftName}.`,
              }
            } else if (event.type === 'meetup_payment.updated') {
              const status = typeof event.data.status === 'string' ? event.data.status : 'updated'
              notification = {
                id: `meetup-${event.id}`,
                icon: HeartHandshake,
                title: 'Meetup payment updated',
                body: `Your meetup payment is now ${status}.`,
              }
              void Promise.all([
                queryClient.invalidateQueries({ queryKey: ['meetup-payments'] }),
                queryClient.invalidateQueries({ queryKey: ['wallet-balance'] }),
                queryClient.invalidateQueries({ queryKey: ['wallet-transactions'] }),
              ])
            } else if (event.type === 'chat.message') {
              void queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
              void queryClient.invalidateQueries({ queryKey: ['chat-messages'] })
            } else if (
              event.type === 'chat.interest'
              && typeof event.data.threadId === 'string'
              && typeof event.data.senderName === 'string'
            ) {
              notification = {
                id: `interest-${event.id}`,
                icon: MessageCircle,
                title: 'Someone showed interest',
                body: `${event.data.senderName} wants to connect with you.`,
                href: `/messages/${encodeURIComponent(event.data.threadId)}`,
              }
              void queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
            }
            if (!notification) continue

            setNotifications((current) => [notification, ...current].slice(0, 20))
            setUnreadCount((current) => current + 1)
            showToast({
              title: notification.title,
              description: event.type === 'wallet.gift_received'
                ? `${notification.body} Redeem it from your wallet.`
                : notification.body,
              variant: event.type === 'wallet.gift_received' ? 'success' : 'info',
            })
          }
        }
      } catch (error) {
        if (!reportedFailure) {
          reportedFailure = true
          showToast({
            title: 'Notifications are delayed',
            description: error instanceof Error ? error.message : 'Could not load notifications.',
            variant: 'error',
          })
        }
        retryDelay = Math.min(retryDelay * 2, 60_000)
      } finally {
        if (!disposed) pollTimer = window.setTimeout(() => void poll(), retryDelay)
      }
    }

    void poll()
    return () => {
      disposed = true
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
    }
  }, [accountId, queryClient, showToast])

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

  const notificationItems = notifications.map(({ id, icon: Icon, title, body, href }) => {
    const content = (
      <>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <span>
          <span className="block text-sm font-semibold text-ink-900">{title}</span>
          <span className="block text-xs text-ink-500">{body}</span>
        </span>
      </>
    )
    const className = 'flex items-start gap-3 px-4 py-3 hover:bg-ink-50'

    return href ? (
      <Link
        key={id}
        to={href}
        role={isMobile ? undefined : 'menuitem'}
        onClick={() => setOpen(false)}
        className={className}
      >
        {content}
      </Link>
    ) : (
      <div key={id} role={isMobile ? undefined : 'menuitem'} className={className}>
        {content}
      </div>
    )
  })

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
            {notificationItems.length ? notificationItems : <p className="px-4 py-3 text-sm text-ink-500">No notifications yet.</p>}
          </div>
        )}
      </div>
      {open && isMobile && (
        <Drawer open onClose={() => setOpen(false)} title="Notifications">
          <div className="-mx-4 -mt-2 divide-y divide-ink-100">
            {notificationItems.length ? notificationItems : <p className="px-4 py-3 text-sm text-ink-500">No notifications yet.</p>}
          </div>
        </Drawer>
      )}
    </>
  )
}
