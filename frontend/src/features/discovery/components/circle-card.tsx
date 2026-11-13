import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { MemberAvatar } from '@/components/ui/member-avatar'
import type { MemberProfile } from '@/lib/api/types'

export function CircleCard({ profile, showDistance }: { profile: MemberProfile; showDistance: boolean }) {
  return (
    <Link
      to={`/profiles/${profile.id}`}
      className="group relative flex flex-col items-center gap-2 rounded-2xl border border-ink-100 bg-white px-3 py-5 text-center shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-float"
    >
      <span className="absolute right-2 top-2 flex size-6 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600 opacity-0 transition-opacity group-hover:opacity-100">
        <ArrowUpRight className="size-3.5" aria-hidden="true" />
      </span>
      <MemberAvatar id={profile.id} name={profile.displayName} photo={profile.photos[0]} size="lg" />
      <div className="min-w-0 w-full">
        <p className="truncate text-sm font-bold text-ink-900">
          {profile.displayName}, {profile.ageRange}
        </p>
        <p className="truncate text-xs text-ink-500">
          {showDistance ? `${profile.distanceKm} km away` : profile.area}
        </p>
      </div>
    </Link>
  )
}
