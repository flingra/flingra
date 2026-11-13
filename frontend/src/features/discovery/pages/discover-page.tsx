import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, LocateFixed, MapPin, Menu as MenuIcon, Minus, Music, Camera, Plus, Trophy, Coffee, Laptop } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { MapBackground } from '@/components/ui/map-background'
import { DEFAULT_FILTERS, getDiscoveryFeed } from '@/lib/api/profiles'
import type { DiscoveryFilters, MemberProfile } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'
import { MapPin as ProfilePin } from '../components/map-pin'
import { CircleCard } from '../components/circle-card'
import { FiltersDrawer } from '../components/filters-drawer'
import { GoogleMapView, isGoogleMapsConfigured } from '../components/google-map-view'

const CATEGORY_CHIPS = [
  { interest: 'Afrobeats', label: 'Afrobeats', icon: Music },
  { interest: 'Photography', label: 'Photography', icon: Camera },
  { interest: 'Football', label: 'Football', icon: Trophy },
  { interest: 'Cooking', label: 'Cooking', icon: Coffee },
  { interest: 'Tech', label: 'Tech', icon: Laptop },
]

export function DiscoverPage() {
  const session = useSessionStore((state) => state.session)
  const [filters, setFilters] = useState<DiscoveryFilters>(DEFAULT_FILTERS)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [locationEnabled, setLocationEnabled] = useState(false)
  const [activeCategories, setActiveCategories] = useState<string[]>([])
  const [profiles, setProfiles] = useState<MemberProfile[]>([])
  const [cursor, setCursor] = useState(0)
  const [zoom, setZoom] = useState(1)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['discover', filters, cursor],
    queryFn: () => getDiscoveryFeed(filters, cursor),
  })

  const allItems = useMemo(
    () => (cursor === 0 ? data?.items ?? [] : [...profiles, ...(data?.items ?? [])]),
    [cursor, data, profiles],
  )
  const items = useMemo(
    () =>
      activeCategories.length === 0
        ? allItems
        : allItems.filter((profile) => profile.interests.some((interest) => activeCategories.includes(interest))),
    [allItems, activeCategories],
  )

  function applyFilters(next: DiscoveryFilters) {
    setFilters(next)
    setCursor(0)
    setProfiles([])
    setFiltersOpen(false)
  }

  function loadMore() {
    if (data) setProfiles(allItems)
    if (data?.nextCursor != null) setCursor(data.nextCursor)
  }

  function toggleCategory(interest: string) {
    setActiveCategories((current) =>
      current.includes(interest) ? current.filter((item) => item !== interest) : [...current, interest],
    )
  }

  function resetAll() {
    setActiveCategories([])
    applyFilters(DEFAULT_FILTERS)
  }

  const googleMapsReady = isGoogleMapsConfigured()

  return (
    <div className="mx-auto max-w-5xl px-4 pb-10 pt-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setFiltersOpen(true)}
          className="flex flex-1 cursor-pointer items-center gap-2 rounded-full bg-white px-4 py-3 text-left shadow-soft transition-shadow hover:shadow-float"
        >
          <MapPin className="size-4 shrink-0 text-primary-500" aria-hidden="true" />
          <span className="flex-1 truncate font-semibold text-ink-900">
            {session?.stage === 'active' ? 'Discovering near you' : 'Set your area'}
          </span>
          <ChevronDown className="size-4 shrink-0 text-ink-400" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => setFiltersOpen(true)}
          aria-label="Open filters"
          className="cursor-pointer rounded-full bg-white p-3.5 text-ink-700 shadow-soft transition-shadow hover:shadow-float"
        >
          <MenuIcon className="size-4" aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
        <button
          type="button"
          onClick={() => setLocationEnabled((current) => !current)}
          aria-pressed={locationEnabled}
          className={`inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
            locationEnabled ? 'border-ink-900 bg-ink-900 text-white' : 'border-ink-200 bg-white text-ink-700 hover:border-ink-300'
          }`}
        >
          <MapPin className="size-4" aria-hidden="true" /> Distance
        </button>
        {CATEGORY_CHIPS.map(({ interest, label, icon: Icon }) => (
          <button
            key={interest}
            type="button"
            onClick={() => toggleCategory(interest)}
            aria-pressed={activeCategories.includes(interest)}
            className={`inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
              activeCategories.includes(interest)
                ? 'border-ink-900 bg-ink-900 text-white'
                : 'border-ink-200 bg-white text-ink-700 hover:border-ink-300'
            }`}
          >
            <Icon className="size-4" aria-hidden="true" /> {label}
          </button>
        ))}
      </div>

      {!googleMapsReady && (
        <p className="mt-3 rounded-2xl bg-ink-100 px-4 py-2.5 text-xs text-ink-500">
          Showing a stylized map. Add <code className="font-mono text-ink-700">VITE_GOOGLE_MAPS_API_KEY</code> (and
          optionally <code className="font-mono text-ink-700">VITE_GOOGLE_MAPS_MAP_ID</code> for the tilted 3D view)
          to <code className="font-mono text-ink-700">frontend/.env.local</code> to switch to the live Google map.
        </p>
      )}

      <div className="relative mt-4 h-[420px] overflow-hidden rounded-3xl shadow-soft sm:h-[480px]">
        {googleMapsReady ? (
          <GoogleMapView profiles={items} highlightedId={items[0]?.id} />
        ) : (
          <div
            className="absolute inset-0 origin-center transition-transform duration-300 ease-out"
            style={{ transform: `scale(${zoom})` }}
          >
            <MapBackground className="absolute inset-0" />
            {!isLoading &&
              !isError &&
              items.map((profile, index) => <ProfilePin key={profile.id} profile={profile} highlighted={index === 0} />)}
          </div>
        )}

        {isLoading && cursor === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/60">
            <Skeleton className="size-16 rounded-full" />
          </div>
        )}

        {isError && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 p-6">
            <ErrorState title="Couldn't load profiles" action={{ label: 'Retry', onClick: () => refetch() }} />
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 p-6">
            <EmptyState
              title="No matches yet"
              description="Try a different category or widen your filters."
              action={{ label: 'Reset filters', onClick: resetAll }}
            />
          </div>
        )}

        {!googleMapsReady && (
          <div className="absolute bottom-4 right-4 flex flex-col items-end gap-2">
            <button
              type="button"
              onClick={() => setLocationEnabled((current) => !current)}
              aria-label="Use my location"
              aria-pressed={locationEnabled}
              className={`flex size-10 cursor-pointer items-center justify-center rounded-full shadow-float transition-colors ${
                locationEnabled ? 'bg-primary-500 text-white' : 'bg-white text-ink-700 hover:bg-ink-50'
              }`}
            >
              <LocateFixed className="size-4" aria-hidden="true" />
            </button>
            <div className="flex flex-col overflow-hidden rounded-full bg-white shadow-float">
              <button
                type="button"
                onClick={() => setZoom((current) => Math.min(1.6, +(current + 0.2).toFixed(2)))}
                aria-label="Zoom in"
                className="flex size-10 cursor-pointer items-center justify-center text-ink-700 hover:bg-ink-50"
              >
                <Plus className="size-4" aria-hidden="true" />
              </button>
              <div className="h-px bg-ink-100" />
              <button
                type="button"
                onClick={() => setZoom((current) => Math.max(1, +(current - 0.2).toFixed(2)))}
                aria-label="Zoom out"
                className="flex size-10 cursor-pointer items-center justify-center text-ink-700 hover:bg-ink-50"
              >
                <Minus className="size-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>

      {items.length > 0 && (
        <div className="-mx-4 mt-4 flex gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
          {items.map((profile) => (
            <CircleCard key={profile.id} profile={profile} showDistance={locationEnabled} />
          ))}
        </div>
      )}

      {data?.nextCursor != null && (
        <div className="mt-6 flex justify-center">
          <Button variant="secondary" loading={isFetching} onClick={loadMore}>
            Load more
          </Button>
        </div>
      )}

      <FiltersDrawer open={filtersOpen} onClose={() => setFiltersOpen(false)} filters={filters} onApply={applyFilters} />
    </div>
  )
}
