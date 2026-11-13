import { Link } from 'react-router-dom'
import { MemberAvatar } from '@/components/ui/member-avatar'
import { cn } from '@/lib/utils'
import type { MemberProfile } from '@/lib/api/types'

/**
 * Deterministic pseudo-scatter so the same profile always lands in the same spot.
 * FNV-1a gives enough avalanche that near-identical ids (e.g. "member-1" vs
 * "member-2") still land far apart, unlike a plain polynomial rolling hash.
 */
function fnv1a(str: string) {
  let hash = 0x811c9dc5
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

export function pinPosition(id: string) {
  const hash = fnv1a(id)
  const top = 12 + ((hash >>> 16) % 70)
  const left = 8 + ((hash & 0xffff) % 78)
  return { top: `${top}%`, left: `${left}%` }
}

export function MapPin({ profile, highlighted }: { profile: MemberProfile; highlighted?: boolean }) {
  const { top, left } = pinPosition(profile.id)

  return (
    <Link
      to={`/profiles/${profile.id}`}
      className="absolute -translate-x-1/2 -translate-y-1/2"
      style={{ top, left }}
      aria-label={`View ${profile.displayName}'s profile`}
    >
      {/* Contact shadow grounds the pin on the map instead of letting it float. */}
      <span
        className={cn(
          'absolute left-1/2 top-full -mt-1 h-2.5 -translate-x-1/2 rounded-full blur-[2px]',
          highlighted ? 'w-10 bg-primary-500/35' : 'w-7 bg-ink-900/20',
        )}
      />
      {highlighted && <span className="absolute inset-0 -m-2.5 animate-ping rounded-full bg-primary-400/30" />}
      <MemberAvatar
        id={profile.id}
        name={profile.displayName}
        photo={profile.photos[0]}
        size={highlighted ? 'lg' : 'md'}
        className={cn(
          'border-4 shadow-float transition-transform hover:scale-105',
          highlighted ? 'border-primary-500' : 'border-white',
        )}
      />
    </Link>
  )
}
