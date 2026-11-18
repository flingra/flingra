import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronDown,
  MapPin,
  Menu as MenuIcon,
  Music,
  Camera,
  Trophy,
  Coffee,
  Laptop,
  Shirt,
  Plane,
  Film,
  Dumbbell,
  PartyPopper,
  Search,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { DEFAULT_FILTERS, getDiscoveryFeed } from '@/lib/api/profiles'
import type { DiscoveryFilters, MemberProfile } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'
import { searchLocations, type LocationSearchResult } from '@/lib/location'
import { CircleCard } from '../components/circle-card'
import { FiltersDrawer } from '../components/filters-drawer'
import { GoogleMapView, OpenStreetMapView, isGoogleMapsConfigured } from '../components/google-map-view'

const CATEGORY_CHIPS = [
  { interest: 'Afrobeats', label: 'Afrobeats', icon: Music },
  { interest: 'Photography', label: 'Photography', icon: Camera },
  { interest: 'Football', label: 'Football', icon: Trophy },
  { interest: 'Cooking', label: 'Cooking', icon: Coffee },
  { interest: 'Tech', label: 'Tech', icon: Laptop },
  { interest: 'Fashion', label: 'Fashion', icon: Shirt },
  { interest: 'Travel', label: 'Travel', icon: Plane },
  { interest: 'Movies', label: 'Movies', icon: Film },
  { interest: 'Fitness', label: 'Fitness', icon: Dumbbell },
  { interest: 'Nightlife', label: 'Nightlife', icon: PartyPopper },
]

export function DiscoverPage() {
  const session = useSessionStore((state) => state.session)
  const [filters, setFilters] = useState<DiscoveryFilters>(DEFAULT_FILTERS)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [locationEnabled, setLocationEnabled] = useState(false)
  const [activeCategories, setActiveCategories] = useState<string[]>([])
  const [profiles, setProfiles] = useState<MemberProfile[]>([])
  const [cursor, setCursor] = useState(0)
  const [locationSearch, setLocationSearch] = useState('')
  const [locationResults, setLocationResults] = useState<LocationSearchResult[]>([])
  const [searchingLocation, setSearchingLocation] = useState(false)
  const [locationError, setLocationError] = useState<string | null>(null)
  const [mapCenter, setMapCenter] = useState<[number, number]>([6.4698, 3.5852])
  const [mapLocationLabel, setMapLocationLabel] = useState('Lekki, Lagos')
  const [locationSearchLocked, setLocationSearchLocked] = useState(false)

  useEffect(() => {
    if (locationSearchLocked) return
    const query = locationSearch.trim()
    if (query.length < 2) {
      setLocationResults([])
      setLocationError(null)
      return
    }

    let cancelled = false
    setSearchingLocation(false)
    setLocationError(null)
    setLocationResults([])
    const timeout = window.setTimeout(async () => {
      setSearchingLocation(true)
      setLocationError(null)
      try {
        const results = await searchLocations(query)
        if (!cancelled) {
          setLocationResults(results)
          if (results.length === 0) setLocationError('No locations found. Try a nearby landmark or street.')
        }
      } catch (error) {
        if (!cancelled) {
          setLocationResults([])
          setLocationError(error instanceof Error ? error.message : 'Location search is unavailable.')
        }
      } finally {
        if (!cancelled) setSearchingLocation(false)
      }
    }, 350)

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [locationSearch, locationSearchLocked])

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

  async function handleLocationSearch() {
    if (locationSearch.trim().length < 2) return
    setSearchingLocation(true)
    setLocationError(null)
    try {
      const results = await searchLocations(locationSearch)
      setLocationResults(results)
      if (results.length === 0) setLocationError('No locations found nearby.')
    } catch (error) {
      setLocationResults([])
      setLocationError(error instanceof Error ? error.message : 'Location search is unavailable.')
    } finally {
      setSearchingLocation(false)
    }
  }

  function selectLocation(result: LocationSearchResult) {
    setLocationSearchLocked(true)
    setSearchingLocation(false)
    setLocationError(null)
    setLocationResults([])
    setMapCenter([result.latitude, result.longitude])
    setMapLocationLabel(result.area)
    setLocationSearch(result.area)
  }

  const googleMapsReady = isGoogleMapsConfigured()

  return (
    <div className="mx-auto max-w-5xl overflow-x-hidden px-4 pb-10 pt-4 sm:px-6">
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

      <div className="relative mt-4 h-[70vh] min-h-[520px] w-full overflow-hidden rounded-[28px] border border-white/80 bg-ink-100 shadow-[10px_10px_30px_rgba(21,18,15,0.12),-8px_-8px_24px_rgba(255,255,255,0.95)] ring-1 ring-ink-900/5">
        <div className="absolute left-1/2 top-4 z-[1200] w-[calc(100%-2rem)] max-w-md -translate-x-1/2">
          <form
            className="flex items-center gap-2 rounded-full border border-ink-100 bg-white p-1.5 pl-3 shadow-float"
            onSubmit={(event) => {
              event.preventDefault()
              void handleLocationSearch()
            }}
          >
            <Search className="size-4 shrink-0 text-ink-400" aria-hidden="true" />
            <input
              aria-label="Search locations"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={locationResults.length > 0}
              value={locationSearch}
              onChange={(event) => {
                setLocationSearchLocked(false)
                setLocationSearch(event.target.value)
              }}
              placeholder="Search a street, landmark, neighbourhood or city"
              className="min-w-0 flex-1 bg-transparent text-sm font-medium text-ink-900 outline-none placeholder:text-ink-400"
            />
            {locationSearch && (
              <button
                type="button"
                aria-label="Clear location search"
                onClick={() => {
                  setLocationSearchLocked(false)
                  setLocationSearch('')
                  setLocationResults([])
                  setLocationError(null)
                  setMapCenter([6.4698, 3.5852])
                  setMapLocationLabel('Lekki, Lagos')
                }}
                className="flex size-8 shrink-0 items-center justify-center rounded-full text-ink-400 hover:bg-ink-100"
              >
                <X className="size-4" />
              </button>
            )}
            <Button type="submit" size="icon" className="size-9 shrink-0 rounded-full" disabled={searchingLocation}>
              <Search className="size-4" />
            </Button>
          </form>

          {(locationResults.length > 0 || locationError || searchingLocation) && (
            <div className="mt-2 max-h-56 overflow-y-auto rounded-2xl border border-ink-100 bg-white p-1 shadow-float">
              {searchingLocation && <p className="px-3 py-2 text-sm text-ink-500" role="status">Searching locations…</p>}
              {locationError && <p className="px-3 py-2 text-sm text-danger" role="alert">{locationError}</p>}
              {locationResults.map((result) => (
                <button
                  key={`${result.latitude}-${result.longitude}-${result.name}`}
                  type="button"
                  onClick={() => selectLocation(result)}
                  className="block w-full rounded-xl px-3 py-2 text-left hover:bg-ink-50"
                >
                  <span className="block text-sm font-semibold text-ink-900">{result.area}</span>
                  <span className="block truncate text-xs text-ink-500">{result.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {googleMapsReady ? (
          <GoogleMapView
            profiles={items}
            highlightedId={items[0]?.id}
            center={{ lat: mapCenter[0], lng: mapCenter[1] }}
            locationLabel={mapLocationLabel}
          />
        ) : (
          <OpenStreetMapView
            profiles={items}
            highlightedId={items[0]?.id}
            useMyLocation={locationEnabled}
            center={mapCenter}
            locationLabel={mapLocationLabel}
          />
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

      </div>

      {items.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
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
