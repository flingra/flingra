import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
import {
  DEFAULT_FILTERS,
  getDiscoveryFeed,
  getOwnProfile,
  publishCurrentLocation,
  stopLocationSharing,
} from '@/lib/api/profiles'
import type { DiscoveryFilters, MemberProfile } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'
import { getCurrentLocation, searchLocations, type CurrentLocation, type LocationSearchResult } from '@/lib/location'
import { CircleCard } from '../components/circle-card'
import { FiltersDrawer } from '../components/filters-drawer'
import { GoogleMapView, OpenStreetMapView, isGoogleMapsConfigured } from '../components/google-map-view'
import { LocationAccessDialog } from '../components/location-access-dialog'

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
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<DiscoveryFilters>(DEFAULT_FILTERS)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [locationEnabled, setLocationEnabled] = useState(false)
  const [userLocation, setUserLocation] = useState<CurrentLocation | null>(null)
  const [locating, setLocating] = useState(false)
  const [activeCategories, setActiveCategories] = useState<string[]>([])
  const [profiles, setProfiles] = useState<MemberProfile[]>([])
  const [cursor, setCursor] = useState(0)
  const [locationSearch, setLocationSearch] = useState('')
  const [locationResults, setLocationResults] = useState<LocationSearchResult[]>([])
  const [searchingLocation, setSearchingLocation] = useState(false)
  const [locationError, setLocationError] = useState<string | null>(null)
  const [locationDialogOpen, setLocationDialogOpen] = useState(false)
  const [locationRequestMessage, setLocationRequestMessage] = useState<string | null>(null)
  const [sharingLocation, setSharingLocation] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [shareLocating, setShareLocating] = useState(false)
  const [shareLocationMessage, setShareLocationMessage] = useState<string | null>(null)
  const locationWatchId = useRef<number | null>(null)
  const lastLocationPublishedAt = useRef(0)
  const sharingLocationRef = useRef(false)
  const [mapCenter, setMapCenter] = useState<[number, number]>([6.4698, 3.5852])
  const [mapLocationLabel, setMapLocationLabel] = useState('Lekki, Lagos')
  const [locationSearchLocked, setLocationSearchLocked] = useState(false)
  const effectiveFilters = useMemo(
    () => (locationEnabled ? filters : { ...filters, maxDistanceKm: 200 }),
    [filters, locationEnabled],
  )
  const activeMapCenter = useMemo<[number, number]>(
    () => (userLocation ? [userLocation.latitude, userLocation.longitude] : mapCenter),
    [mapCenter, userLocation],
  )
  const activeMapLocationLabel = userLocation ? 'Your location' : mapLocationLabel
  const { data: ownProfile } = useQuery({
    queryKey: ['own-profile'],
    queryFn: getOwnProfile,
    retry: false,
  })

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
      } catch {
        if (!cancelled) {
          setLocationResults([])
          setLocationError('Location search is temporarily unavailable. Choose an area on the map instead.')
        }
      } finally {
        if (!cancelled) setSearchingLocation(false)
      }
    }, 1100)

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [locationSearch, locationSearchLocked])

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: [
      'discover',
      effectiveFilters,
      activeMapCenter[0],
      activeMapCenter[1],
      locationEnabled,
      cursor,
    ],
    queryFn: () =>
      getDiscoveryFeed(
        effectiveFilters,
        cursor,
        { latitude: activeMapCenter[0], longitude: activeMapCenter[1] },
        locationEnabled,
      ),
    refetchInterval: cursor === 0 ? 30_000 : false,
    refetchIntervalInBackground: false,
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

  function watchSharedLocation() {
    if (!navigator.geolocation || locationWatchId.current !== null) return
    locationWatchId.current = navigator.geolocation.watchPosition(
      ({ coords }) => {
        const now = Date.now()
        if (now - lastLocationPublishedAt.current < 30_000) return
        lastLocationPublishedAt.current = now
        void publishCurrentLocation({
          latitude: coords.latitude,
          longitude: coords.longitude,
        })
          .then(() => {
            setShareLocationMessage(null)
            void queryClient.invalidateQueries({ queryKey: ['discover'] })
            void queryClient.invalidateQueries({ queryKey: ['own-profile'] })
          })
          .catch(() => {
            setShareLocationMessage('Location updates are paused. Check your connection or turn sharing off.')
          })
      },
      () => {
        if (locationWatchId.current !== null) {
          navigator.geolocation.clearWatch(locationWatchId.current)
          locationWatchId.current = null
        }
        sharingLocationRef.current = false
        setSharingLocation(false)
        setShareLocationMessage('Live sharing paused. Turn it on again to resume location updates.')
        void stopLocationSharing().catch(() => {
          setShareLocationMessage('Sharing will expire automatically if location updates stop.')
        })
      },
      { enableHighAccuracy: true, maximumAge: 15_000, timeout: 30_000 },
    )
  }

  useEffect(() => {
    if (!ownProfile?.locationSharingEnabled || sharingLocationRef.current) return
    sharingLocationRef.current = true
    setSharingLocation(true)
    lastLocationPublishedAt.current = 0
    watchSharedLocation()
  }, [ownProfile?.locationSharingEnabled])

  useEffect(() => {
    return () => {
      if (locationWatchId.current !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(locationWatchId.current)
      }
    }
  }, [])

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

  function toggleDistanceFilter() {
    if (locationEnabled) {
      setLocationEnabled(false)
      setUserLocation(null)
      setCursor(0)
      setProfiles([])
      return
    }

    setLocationRequestMessage(null)
    setLocationDialogOpen(true)
  }

  async function requestNearbyLocation() {
    setLocationRequestMessage(null)
    setLocating(true)
    try {
      const location = await getCurrentLocation()
      setUserLocation(location)
      setLocationEnabled(true)
      setCursor(0)
      setProfiles([])
      setLocationDialogOpen(false)
    } catch {
      setLocationRequestMessage('We couldn’t get a location fix this time. Try again or choose an area on the map.')
    } finally {
      setLocating(false)
    }
  }

  function toggleLocationSharing() {
    if (sharingLocation) {
      void disableLocationSharing()
      return
    }
    setShareLocationMessage(null)
    setShareDialogOpen(true)
  }

  async function enableLocationSharing() {
    setShareLocationMessage(null)
    setShareLocating(true)
    try {
      const location = await getCurrentLocation()
      await publishCurrentLocation(location)
      sharingLocationRef.current = true
      lastLocationPublishedAt.current = Date.now()
      setSharingLocation(true)
      setShareDialogOpen(false)
      watchSharedLocation()
      await queryClient.invalidateQueries({ queryKey: ['discover'] })
      await queryClient.invalidateQueries({ queryKey: ['own-profile'] })
    } catch {
      setShareLocationMessage('Could not start location sharing. Try again or keep exploring by chosen area.')
    } finally {
      setShareLocating(false)
    }
  }

  async function disableLocationSharing() {
    setShareLocating(true)
    if (locationWatchId.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(locationWatchId.current)
      locationWatchId.current = null
    }
    sharingLocationRef.current = false
    setSharingLocation(false)
    try {
      await stopLocationSharing()
      setShareLocationMessage('Your live location is no longer shared.')
      await queryClient.invalidateQueries({ queryKey: ['discover'] })
      await queryClient.invalidateQueries({ queryKey: ['own-profile'] })
    } catch {
      setShareLocationMessage('Sharing will expire automatically if location updates stop.')
    } finally {
      setShareLocating(false)
    }
  }

  async function handleLocationSearch() {
    if (locationSearch.trim().length < 2) return
    setLocationSearchLocked(true)
    setSearchingLocation(true)
    setLocationError(null)
    try {
      const results = await searchLocations(locationSearch)
      setLocationResults(results)
      if (results.length === 0) setLocationError('No locations found nearby.')
    } catch {
      setLocationResults([])
      setLocationError('Location search is temporarily unavailable. Choose an area on the map instead.')
    } finally {
      setSearchingLocation(false)
    }
  }

  function selectLocation(result: LocationSearchResult) {
    setLocationEnabled(false)
    setUserLocation(null)
    setCursor(0)
    setProfiles([])
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
          onClick={() => void toggleDistanceFilter()}
          disabled={locating}
          aria-pressed={locationEnabled}
          className={`inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
            locationEnabled ? 'border-ink-900 bg-ink-900 text-white' : 'border-ink-200 bg-white text-ink-700 hover:border-ink-300'
          }`}
        >
          <MapPin className="size-4" aria-hidden="true" /> {locating ? 'Locating…' : 'Distance'}
        </button>
        <button
          type="button"
          onClick={toggleLocationSharing}
          disabled={shareLocating}
          aria-pressed={sharingLocation}
          className={`inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
            sharingLocation
              ? 'border-primary-600 bg-primary-600 text-white'
              : 'border-ink-200 bg-white text-ink-700 hover:border-ink-300'
          }`}
        >
          <MapPin className="size-4" aria-hidden="true" />
          {shareLocating ? 'Updating…' : sharingLocation ? 'Sharing location' : 'Share location'}
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
      {shareLocationMessage && (
        <p className="mt-2 text-sm text-ink-500" role="status">{shareLocationMessage}</p>
      )}
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
              {locationError && <p className="px-3 py-2 text-sm text-ink-500" role="status">{locationError}</p>}
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
            center={{ lat: activeMapCenter[0], lng: activeMapCenter[1] }}
            locationLabel={activeMapLocationLabel}
            userLocation={userLocation}
          />
        ) : (
          <OpenStreetMapView
            profiles={items}
            highlightedId={items[0]?.id}
            center={activeMapCenter}
            userLocation={userLocation ?? undefined}
            locationLabel={activeMapLocationLabel}
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

      <FiltersDrawer
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        filters={filters}
        onApply={applyFilters}
        distanceEnabled={locationEnabled}
      />
      <LocationAccessDialog
        open={locationDialogOpen}
        locating={locating}
        message={locationRequestMessage}
        onClose={() => setLocationDialogOpen(false)}
        onAllow={() => void requestNearbyLocation()}
        onChooseManually={() => {
          setLocationDialogOpen(false)
          setLocationRequestMessage(null)
        }}
      />
      <LocationAccessDialog
        open={shareDialogOpen}
        locating={shareLocating}
        message={shareLocationMessage}
        title="Share your current location?"
        description="People who discover profiles around your area can find you while sharing is on."
        privacyMessage="Your exact coordinates are never shown. Others see an approximate area and distance. Sharing stops when you turn it off or location updates expire after 5 minutes."
        actionLabel="Start sharing"
        onClose={() => setShareDialogOpen(false)}
        onAllow={() => void enableLocationSharing()}
        onChooseManually={() => {
          setShareDialogOpen(false)
          setShareLocationMessage(null)
        }}
      />
    </div>
  )
}
