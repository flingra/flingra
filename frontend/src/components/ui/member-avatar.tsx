import { Radio } from 'lucide-react'
import { Avatar } from './avatar'
import { cn } from '@/lib/utils'
import { getPresence } from '@/lib/api/presence'

type AvatarSize = 'sm' | 'md' | 'lg' | 'xl'

/**
 * Avatar decorated with the member's presence: a pulsing orange ring when they
 * have an active status, or a circulating ring plus a small "LIVE" badge when
 * they're currently livestreaming.
 */
export function MemberAvatar({
  id,
  name,
  photo,
  size = 'md',
  className,
}: {
  id: string
  name: string
  photo?: string
  size?: AvatarSize
  className?: string
}) {
  const { hasStatus, isLive } = getPresence(id)

  return (
    <span className="relative inline-flex shrink-0">
      {/* Ring sits behind the avatar and rotates on its own, so the photo itself never spins. */}
      {isLive && (
        <span
          aria-hidden="true"
          className="absolute inset-[-3px] animate-spin rounded-full bg-gradient-to-tr from-primary-500 via-amber-400 to-primary-600"
          style={{ animationDuration: '2.5s' }}
        />
      )}
      {!isLive && hasStatus && (
        <span aria-hidden="true" className="absolute inset-[-3px] animate-pulse rounded-full bg-primary-500" />
      )}
      <Avatar name={name} src={photo} size={size} className={cn('relative', (isLive || hasStatus) && 'ring-2 ring-white', className)} />
      {isLive && (
        <span className="absolute -bottom-1.5 left-1/2 flex -translate-x-1/2 items-center gap-0.5 whitespace-nowrap rounded-full bg-danger px-1.5 py-0.5 text-[9px] font-bold leading-none text-white shadow-soft">
          <Radio className="size-2.5" aria-hidden="true" /> LIVE
        </span>
      )}
    </span>
  )
}
