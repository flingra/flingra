import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Crown, MapPin, Radio } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { listLiveStreamsNearby } from '@/lib/api/livestream'

export function LivestreamsPage() {
  const { data: streams, isLoading } = useQuery({ queryKey: ['livestreams-nearby'], queryFn: listLiveStreamsNearby })

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
        <Radio className="size-6 text-danger" aria-hidden="true" /> Live now
      </h1>
      <p className="mt-1 text-sm text-ink-500">Livestreams from members near you, closest first.</p>

      {isLoading && <PageSpinner label="Loading livestreams" />}

      {streams && streams.length === 0 && (
        <div className="mt-6">
          <EmptyState title="No one is live right now" description="Check back soon, or explore Discover in the meantime." />
        </div>
      )}

      {streams && streams.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {streams.map((stream) => (
            <Link
              key={stream.id}
              to={`/live/${stream.id}`}
              className="group flex items-center gap-3 rounded-2xl border border-ink-100 bg-white p-3 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-float"
            >
              <div className="relative shrink-0">
                <span
                  aria-hidden="true"
                  className="absolute inset-[-3px] animate-spin rounded-full bg-gradient-to-tr from-primary-500 via-amber-400 to-primary-600"
                  style={{ animationDuration: '2.5s' }}
                />
                <Avatar name={stream.hostName} src={stream.hostPhoto} size="lg" className="relative ring-2 ring-white" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 truncate font-bold text-ink-900">
                  {stream.hostName}
                  {stream.hostSubscriptionTier === 'vip' && <Crown className="size-3.5 shrink-0 text-amber-500" aria-hidden="true" />}
                </p>
                <p className="truncate text-sm text-ink-600">{stream.title}</p>
                <p className="mt-0.5 flex items-center gap-1 text-xs text-ink-400">
                  <MapPin className="size-3" aria-hidden="true" /> {stream.hostArea} · {stream.hostDistanceKm} km away
                </p>
              </div>
              <Badge variant="danger" className="shrink-0">
                LIVE
              </Badge>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
