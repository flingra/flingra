import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { MemberAvatar } from '@/components/ui/member-avatar'
import type { MemberProfile } from '@/lib/api/types'

export function CircleCard({ profile, showDistance }: { profile: MemberProfile; showDistance: boolean }) {
  return (
    <Link
      to={`/profiles/${profile.id}`}
      className="group flex shrink-0 items-center gap-3 rounded-full border border-ink-100 bg-white py-2 pl-2 pr-3 shadow-soft transition-shadow hover:shadow-float"
    >
      <MemberAvatar id={profile.id} name={profile.displayName} photo={profile.photos[0]} size="md" />
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-ink-900">
          {profile.displayName}, {profile.ageRange}
        </p>
        <p className="truncate text-xs text-ink-500">
          {showDistance ? `${profile.distanceKm} km away` : profile.area}
        </p>
      </div>
      <span className="ml-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-500 text-white transition-colors group-hover:bg-primary-600">
        <ArrowUpRight className="size-4" aria-hidden="true" />
      </span>
    </Link>
  )
}
