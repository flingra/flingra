import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Camera,
  ChevronDown,
  Coffee,
  Dumbbell,
  Film,
  Laptop,
  MapPin,
  Music,
  PartyPopper,
  Plane,
  Search,
  Shirt,
  SlidersHorizontal,
  Trophy,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Avatar } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import {
  DEFAULT_FILTERS,
  getDiscoveryFeed,
  getOwnProfile,
  publishCurrentLocation,
  searchDiscoverableProfiles,
  stopLocationSharing,
} from '@/lib/api/profiles'
import type { DiscoveryFilters, MemberProfile, ProfileSearchResult } from '@/lib/api/types'
import { getCurrentLocation, searchLocations, type CurrentLocation, type LocationSearchResult } from '@/lib/location'
import { CircleCard } from '../components/circle-card'
import { FiltersDrawer } from '../components/filters-drawer'
import { GoogleMapView, isGoogleMapsConfigured } from '../components/google-map-view'
import { LocationAccessDialog } from '../components/location-access-dialog'

const CATEGORY_CHIPS: { interest: string; label: string; icon: LucideIcon }[] = [
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

const FALLBACK_MAP_CENTER: [number, number] = [9.076, 7.398]
const FEED_REFRESH_MS = 30_000
const SEARCH_DEBOUNCE_MS = 400
const SHARE_PUBLISH_INTERVAL_MS = 30_000
const SEARCH_UNAVAILABLE = 'Location search is temporarily unavailable. Try again in a moment.'
const SEARCH_NO_RESULTS = 'No locations found. Try a nearby landmark or street.'
const PROFILE_SEARCH_UNAVAILABLE = 'People search is temporarily unavailable. Try again in a moment.'
const PROFILE_SEARCH_NO_RESULTS = 'No matching profiles found.'

/* -------------------------------------------------------------------------- */
/*  Small presentational pieces                                               */
/* -------------------------------------------------------------------------- */

const CHIP_BASE =
  'inline-flex shrink-0 snap-start cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:px-4 sm:py-2 sm:text-sm'
const CHIP_TONES = {
  off: 'border-ink-200 bg-white text-ink-700 hover:border-ink-300',
  ink: 'border-ink-900 bg-ink-900 text-white',
  brand: 'border-primary-600 bg-primary-600 text-white',
} as const

function FilterChip({
  pressed,
  tone = 'ink',
  icon: Icon,
  disabled,
  onClick,
  children,
}: {
  pressed: boolean
  tone?: 'ink' | 'brand'
  icon: LucideIcon
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      className={`${CHIP_BASE} ${pressed ? CHIP_TONES[tone] : CHIP_TONES.off}`}
    >
      <Icon className="size-4" aria-hidden="true" />
      {children}
    </button>
  )
}

function DiscoveryCardSkeleton() {
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-2xl border border-ink-100 bg-white px-3 py-5 shadow-soft"
      aria-hidden="true"
    >
      <Skeleton className="size-16 rounded-full" />
      <div className="flex w-full flex-col items-center gap-2">
        <Skeleton className="h-4 w-24 max-w-full" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  Hooks                                                                     */
/* -------------------------------------------------------------------------- */

/** Debounced place search with stale-response protection and keyboard-selectable results. */
function useLocationSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<LocationSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [locked, setLocked] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const requestId = useRef(0)

  const run = useCallback(async (text: string) => {
    const id = ++requestId.current
    setSearching(true)
    setError(null)
    try {
      const found = await searchLocations(text)
      if (id !== requestId.current) return
      setResults(found)
      if (found.length === 0) setError(SEARCH_NO_RESULTS)
    } catch {
      if (id !== requestId.current) return
      setResults([])
      setError(SEARCH_UNAVAILABLE)
    } finally {
      if (id === requestId.current) setSearching(false)
    }
  }, [])

  useEffect(() => {
    if (locked) return
    const text = query.trim()
    if (text.length < 2) {
      requestId.current++
      setResults([])
      setError(null)
      setSearching(false)
      return
    }
    const timeout = window.setTimeout(() => void run(text), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timeout)
  }, [query, locked, run])

  useEffect(() => setActiveIndex(-1), [results])

  const reset = useCallback(() => {
    requestId.current++
    setResults([])
    setError(null)
    setSearching(false)
  }, [])

  return {
    query,
    results,
    searching,
    error,
    activeIndex,
    setActiveIndex,
    isOpen: results.length > 0 || searching || error !== null,
    change(value: string) {
      requestId.current++
      setSearching(false)
      setLocked(false)
      setQuery(value)
    },
    submit() {
      const text = query.trim()
      if (text.length < 2) return
      setLocked(true)
      void run(text)
    },
    choose(label: string) {
      setLocked(true)
      reset()
      setQuery(label)
    },
    dismiss: reset,
    clear() {
      setLocked(false)
      setQuery('')
      reset()
    },
  }
}

function useProfileSearch(filters: Pick<DiscoveryFilters, 'minAge' | 'maxAge' | 'lookingFor'>) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ProfileSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [locked, setLocked] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const requestId = useRef(0)

  useEffect(() => {
    requestId.current++
    setLocked(false)
  }, [filters])

  const run = useCallback(async (text: string) => {
    const id = ++requestId.current
    setSearching(true)
    setError(null)
    try {
      const found = await searchDiscoverableProfiles(text, filters)
      if (id !== requestId.current) return
      setResults(found)
      if (found.length === 0) setError(PROFILE_SEARCH_NO_RESULTS)
    } catch (error) {
      if (id !== requestId.current) return
      setResults([])
      setError(error instanceof Error ? error.message : PROFILE_SEARCH_UNAVAILABLE)
    } finally {
      if (id === requestId.current) setSearching(false)
    }
  }, [filters])

  useEffect(() => {
    if (locked) return
    const text = query.trim()
    if (text.replace(/^@/, '').length < 2) {
      requestId.current++
      setResults([])
      setError(null)
      setSearching(false)
      return
    }
    const timeout = window.setTimeout(() => void run(text), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timeout)
  }, [query, locked, run])

  useEffect(() => setActiveIndex(-1), [results])

  const reset = useCallback(() => {
    requestId.current++
    setResults([])
    setError(null)
    setSearching(false)
  }, [])

  return {
    query,
    results,
    searching,
    error,
    activeIndex,
    setActiveIndex,
    isOpen: results.length > 0 || searching || error !== null,
    change(value: string) {
      requestId.current++
      setSearching(false)
      setLocked(false)
      setQuery(value)
    },
    submit() {
      const text = query.trim()
      if (text.replace(/^@/, '').length < 2) return
      setLocked(true)
      void run(text)
    },
    dismiss: reset,
    clear() {
      setLocked(false)
      setQuery('')
      reset()
    },
  }
}

/** Live location sharing: publishes on a throttle, stops cleanly, and resumes if the server says sharing is on. */
function useLocationSharing(serverEnabled: boolean | undefined) {
  const queryClient = useQueryClient()
  const [sharing, setSharing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const watchId = useRef<number | null>(null)
  const lastPublishedAt = useRef(0)
  const active = useRef(false)

  const refresh = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['discover'] }),
      queryClient.invalidateQueries({ queryKey: ['own-profile'] }),
    ])
  }, [queryClient])

  const clearWatch = useCallback(() => {
    if (watchId.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId.current)
    }
    watchId.current = null
  }, [])

  const markStopped = useCallback(() => {
    clearWatch()
    active.current = false
    setSharing(false)
  }, [clearWatch])

  const startWatch = useCallback(() => {
    if (!navigator.geolocation || watchId.current !== null) return
    watchId.current = navigator.geolocation.watchPosition(
      ({ coords }) => {
        const now = Date.now()
        if (now - lastPublishedAt.current < SHARE_PUBLISH_INTERVAL_MS) return
        lastPublishedAt.current = now
        publishCurrentLocation({ latitude: coords.latitude, longitude: coords.longitude })
          .then(() => {
            setMessage(null)
            void refresh()
          })
          .catch(() => setMessage('Location updates are paused. Check your connection or turn sharing off.'))
      },
      (error) => {
        if (error.code !== error.PERMISSION_DENIED) {
          setMessage('Waiting for a fresh location update. Sharing expires automatically if updates stop.')
          return
        }
        markStopped()
        setMessage('Location permission was removed. Turn sharing on again to resume updates.')
        stopLocationSharing().catch(() =>
          setMessage('Sharing will expire automatically if location updates stop.'),
        )
      },
      { enableHighAccuracy: true, maximumAge: 15_000, timeout: 30_000 },
    )
  }, [markStopped, refresh])

  // Resume when the profile says sharing is already on (e.g. after a reload).
  useEffect(() => {
    if (!serverEnabled || active.current) return
    active.current = true
    setSharing(true)
    lastPublishedAt.current = 0
    startWatch()
  }, [serverEnabled, startWatch])

  useEffect(() => clearWatch, [clearWatch])

  const start = useCallback(async () => {
    setMessage(null)
    setBusy(true)
    try {
      const location = await getCurrentLocation()
      await publishCurrentLocation(location)
      active.current = true
      lastPublishedAt.current = Date.now()
      setSharing(true)
      startWatch()
      void refresh()
      return true
    } catch {
      setMessage('Could not start location sharing. Try again or keep exploring by chosen area.')
      return false
    } finally {
      setBusy(false)
    }
  }, [refresh, startWatch])

  const stop = useCallback(async () => {
    setBusy(true)
    markStopped()
    try {
      await stopLocationSharing()
      setMessage('Your live location is no longer shared.')
      void refresh()
    } catch {
      setMessage('Sharing will expire automatically if location updates stop.')
    } finally {
      setBusy(false)
    }
  }, [markStopped, refresh])

  return { sharing, busy, message, setMessage, start, stop }
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

export function DiscoverPage() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState<DiscoveryFilters>(DEFAULT_FILTERS)
  const [searchMode, setSearchMode] = useState<'location' | 'people'>('location')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [locationEnabled, setLocationEnabled] = useState(false)
  const [userLocation, setUserLocation] = useState<CurrentLocation | null>(null)
  const [locating, setLocating] = useState(false)
  const [profiles, setProfiles] = useState<MemberProfile[]>([])
  const [cursor, setCursor] = useState(0)
  const [locationDialogOpen, setLocationDialogOpen] = useState(false)
  const [locationRequestMessage, setLocationRequestMessage] = useState<string | null>(null)
  const [currentLocationMessage, setCurrentLocationMessage] = useState<string | null>(null)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [mapCenter, setMapCenter] = useState<[number, number] | null>(null)
  const [mapLocationLabel, setMapLocationLabel] = useState('')

  const initialLocationRequest = useRef<Promise<CurrentLocation> | null>(null)
  const manualMapLocationSelected = useRef(false)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const mapRef = useRef<HTMLDivElement>(null)
  const listboxId = useId()

  const search = useLocationSearch()
  const peopleSearch = useProfileSearch(filters)

  const { data: ownProfile } = useQuery({
    queryKey: ['own-profile'],
    queryFn: getOwnProfile,
    retry: false,
  })
  const share = useLocationSharing(ownProfile?.locationSharingEnabled)

  /* ---- derived map state (memoised so the map doesn't re-centre on every render) ---- */

  const savedLat = ownProfile?.latitude
  const savedLng = ownProfile?.longitude
  const savedMapCenter = useMemo<[number, number] | null>(
    () => (savedLat != null && savedLng != null ? [savedLat, savedLng] : null),
    [savedLat, savedLng],
  )
  const activeMapCenter = useMemo<[number, number]>(
    () =>
      userLocation
        ? [userLocation.latitude, userLocation.longitude]
        : (mapCenter ?? savedMapCenter ?? FALLBACK_MAP_CENTER),
    [mapCenter, savedMapCenter, userLocation],
  )
  const mapCenterProp = useMemo(
    () => ({ lat: activeMapCenter[0], lng: activeMapCenter[1] }),
    [activeMapCenter],
  )
  const hasChosenArea = Boolean(userLocation || mapLocationLabel || (savedMapCenter && ownProfile?.area))
  const activeMapLocationLabel = userLocation
    ? 'Your current location'
    : mapLocationLabel || (savedMapCenter ? (ownProfile?.area ?? '') : '') || 'Choose an area'
  const discoveryOrigin = useMemo(
    () => ({ latitude: activeMapCenter[0], longitude: activeMapCenter[1] }),
    [activeMapCenter],
  )
  const hasOrigin = Boolean(userLocation || mapCenter || savedMapCenter)

  const effectiveFilters = useMemo(
    () => (locationEnabled ? filters : { ...filters, maxDistanceKm: 200 }),
    [filters, locationEnabled],
  )
  const activeFilterCount = useMemo(() => {
    const strip = (f: DiscoveryFilters) => JSON.stringify({ ...f, interests: [] })
    return filters.interests.length + (strip(filters) !== strip(DEFAULT_FILTERS) ? 1 : 0)
  }, [filters])

  /* ---- initial location fix ---- */

  useEffect(() => {
    let active = true
    setCurrentLocationMessage('Requesting your current location…')
    initialLocationRequest.current ??= getCurrentLocation()
    initialLocationRequest.current
      .then((location) => {
        if (!active || manualMapLocationSelected.current) return
        setUserLocation(location)
        resetPaging()
        setCurrentLocationMessage(null)
      })
      .catch(() => {
        if (!active || manualMapLocationSelected.current) return
        setCurrentLocationMessage(
          'Location is unavailable. Showing your saved area if available; search for a place to choose another area.',
        )
      })
    return () => {
      active = false
    }
  }, [])

  /* ---- feed ---- */

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['discover', effectiveFilters, activeMapCenter[0], activeMapCenter[1], locationEnabled, cursor],
    queryFn: () =>
      getDiscoveryFeed(effectiveFilters, cursor, hasOrigin ? discoveryOrigin : undefined, locationEnabled),
    refetchInterval: cursor === 0 ? FEED_REFRESH_MS : false,
    refetchIntervalInBackground: false,
  })

  const items = useMemo(
    () => (cursor === 0 ? (data?.items ?? []) : [...profiles, ...(data?.items ?? [])]),
    [cursor, data, profiles],
  )

  /* ---- actions ---- */

  function resetPaging() {
    setCursor(0)
    setProfiles([])
  }

  function applyFilters(next: DiscoveryFilters) {
    setFilters({ ...next, interests: [...new Set(next.interests)] })
    resetPaging()
    setFiltersOpen(false)
  }

  function loadMore() {
    if (data) setProfiles(items)
    if (data?.nextCursor != null) setCursor(data.nextCursor)
  }

  function toggleCategory(interest: string) {
    const interests = filters.interests.includes(interest)
      ? filters.interests.filter((item) => item !== interest)
      : [...filters.interests, interest]
    applyFilters({ ...filters, interests })
  }

  function resetAll() {
    setLocationEnabled(false)
    applyFilters(DEFAULT_FILTERS)
  }

  function clearInterestFilters() {
    applyFilters({ ...filters, interests: [] })
  }

  function toggleDistanceFilter() {
    if (locationEnabled) {
      setLocationEnabled(false)
      resetPaging()
      return
    }
    if (hasOrigin) {
      setLocationEnabled(true)
      resetPaging()
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
      manualMapLocationSelected.current = true
      setUserLocation(location)
      setLocationEnabled(true)
      resetPaging()
      setCurrentLocationMessage(null)
      setLocationDialogOpen(false)
    } catch {
      setLocationRequestMessage('We couldn’t get a location fix this time. Try again or search for an area.')
    } finally {
      setLocating(false)
    }
  }

  function toggleLocationSharing() {
    if (share.sharing) {
      void share.stop()
      return
    }
    share.setMessage(null)
    setShareDialogOpen(true)
  }

  async function enableLocationSharing() {
    if (await share.start()) setShareDialogOpen(false)
  }

  function selectLocation(result: LocationSearchResult) {
    manualMapLocationSelected.current = true
    setLocationEnabled(false)
    setUserLocation(null)
    resetPaging()
    setMapCenter([result.latitude, result.longitude])
    setMapLocationLabel(result.area)
    setCurrentLocationMessage(null)
    search.choose(result.area)
    searchInputRef.current?.blur()
  }

  function selectProfile(profile: ProfileSearchResult) {
    peopleSearch.clear()
    searchInputRef.current?.blur()
    navigate(`/profiles/${encodeURIComponent(profile.id)}`)
  }

  function changeSearchMode(mode: 'location' | 'people') {
    setSearchMode(mode)
    search.clear()
    peopleSearch.clear()
  }

  function clearLocationSearch() {
    manualMapLocationSelected.current = true
    setMapCenter(null)
    setMapLocationLabel('')
    setCurrentLocationMessage(null)
    search.clear()
    searchInputRef.current?.focus()
  }

  function focusSearch() {
    mapRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    searchInputRef.current?.focus({ preventScroll: true })
  }

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    const activeSearch = searchMode === 'location' ? search : peopleSearch
    const count = activeSearch.results.length
    if (event.key === 'Escape') {
      activeSearch.dismiss()
      return
    }
    if (count === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      activeSearch.setActiveIndex((index) => (index + 1) % count)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      activeSearch.setActiveIndex((index) => (index <= 0 ? count - 1 : index - 1))
    } else if (event.key === 'Enter' && activeSearch.activeIndex >= 0) {
      event.preventDefault()
      if (searchMode === 'location') selectLocation(search.results[activeSearch.activeIndex])
      else selectProfile(peopleSearch.results[activeSearch.activeIndex])
    }
  }

  /* ---- render ---- */

  const activeSearch = searchMode === 'location' ? search : peopleSearch
  const googleMapsReady = isGoogleMapsConfigured()
  const showEmpty = !isLoading && !isError && items.length === 0
  const heading = userLocation ? 'Near you' : hasChosenArea ? `In ${activeMapLocationLabel}` : 'People to meet'
  const statusNotes = [share.message, currentLocationMessage].filter((note): note is string => Boolean(note))

  return (
    <div className="mx-auto max-w-5xl overflow-x-hidden px-3 pb-8 pt-3 sm:px-6 sm:pb-10 sm:pt-4">
      {/* Top bar */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={focusSearch}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-full bg-white px-3 py-2.5 text-left shadow-soft transition-shadow hover:shadow-float focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 sm:px-4 sm:py-3"
        >
          <MapPin className="size-4 shrink-0 text-primary-500" aria-hidden="true" />
          <span className="flex-1 truncate font-semibold text-ink-900">{activeMapLocationLabel}</span>
          <ChevronDown className="size-4 shrink-0 text-ink-400" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => setFiltersOpen(true)}
          aria-label={activeFilterCount > 0 ? `Open filters, ${activeFilterCount} active` : 'Open filters'}
          className="relative cursor-pointer rounded-full bg-white p-3 text-ink-700 shadow-soft transition-shadow hover:shadow-float focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 sm:p-3.5"
        >
          <SlidersHorizontal className="size-4" aria-hidden="true" />
          {activeFilterCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex size-5 items-center justify-center rounded-full bg-primary-600 text-[11px] font-semibold text-white">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {/* Chips */}
      <div
        className="-mx-3 mt-3 flex snap-x gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none] sm:mx-0 sm:mt-4 sm:px-0 [&::-webkit-scrollbar]:hidden"
        role="group"
        aria-label="Quick filters"
      >
        <FilterChip icon={MapPin} pressed={locationEnabled} disabled={locating} onClick={toggleDistanceFilter}>
          {locating ? 'Locating…' : 'Distance'}
        </FilterChip>
        <FilterChip
          icon={MapPin}
          tone="brand"
          pressed={share.sharing}
          disabled={share.busy}
          onClick={toggleLocationSharing}
        >
          {share.busy ? 'Updating…' : share.sharing ? 'Sharing location' : 'Share location'}
        </FilterChip>
        {filters.interests.length > 0 && (
          <button
            type="button"
            onClick={clearInterestFilters}
            className={`${CHIP_BASE} ${CHIP_TONES.off} text-ink-500`}
          >
            <X className="size-4" aria-hidden="true" />
            Clear {filters.interests.length}
          </button>
        )}
        {CATEGORY_CHIPS.map(({ interest, label, icon }) => (
          <FilterChip
            key={interest}
            icon={icon}
            pressed={filters.interests.includes(interest)}
            onClick={() => toggleCategory(interest)}
          >
            {label}
          </FilterChip>
        ))}
      </div>

      {/* Status notes */}
      {statusNotes.length > 0 && (
        <div className="mt-2 space-y-1" role="status">
          {statusNotes.map((note) => (
            <p key={note} className="text-sm text-ink-500">
              {note}
            </p>
          ))}
        </div>
      )}
      {data?.distanceExpanded && (
        <p className="mt-2 rounded-xl bg-primary-50 px-3 py-2 text-sm text-primary-800" role="status">
          No eligible profiles are within this distance. Showing verified profiles from other locations, nearest first.
        </p>
      )}

      {/* Map */}
      <div
        ref={mapRef}
        className="relative mt-3 h-[54dvh] max-h-[480px] min-h-[360px] w-full overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-sm sm:mt-4 sm:h-[70vh] sm:max-h-none sm:min-h-[520px]"
      >
        <div className="absolute left-1/2 top-3 z-[1200] w-[calc(100%-1.5rem)] max-w-md -translate-x-1/2 sm:top-4 sm:w-[calc(100%-2rem)]">
          <div
            role="group"
            aria-label="Search filter"
            className="mb-2 flex rounded-full border border-ink-100 bg-white/95 p-1 shadow-md backdrop-blur"
          >
            <button
              type="button"
              aria-pressed={searchMode === 'location'}
              onClick={() => changeSearchMode('location')}
              className={`flex-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                searchMode === 'location' ? 'bg-ink-900 text-white' : 'text-ink-600 hover:bg-ink-50'
              }`}
            >
              Location
            </button>
            <button
              type="button"
              aria-pressed={searchMode === 'people'}
              onClick={() => changeSearchMode('people')}
              className={`flex-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                searchMode === 'people' ? 'bg-ink-900 text-white' : 'text-ink-600 hover:bg-ink-50'
              }`}
            >
              Username
            </button>
          </div>
          <form
            className="flex items-center gap-2 rounded-full border border-ink-100 bg-white/95 p-1.5 pl-3 shadow-md backdrop-blur focus-within:ring-2 focus-within:ring-primary-500"
            onSubmit={(event) => {
              event.preventDefault()
              if (searchMode === 'location') search.submit()
              else peopleSearch.submit()
            }}
          >
            <Search className="size-4 shrink-0 text-ink-400" aria-hidden="true" />
            <input
              ref={searchInputRef}
              type="text"
              role="combobox"
              aria-label={searchMode === 'location' ? 'Search locations' : 'Search by username or display name'}
              aria-autocomplete="list"
              aria-expanded={activeSearch.isOpen}
              aria-controls={listboxId}
              aria-activedescendant={
                activeSearch.activeIndex >= 0 ? `${listboxId}-${activeSearch.activeIndex}` : undefined
              }
              autoComplete="off"
              enterKeyHint="search"
              value={activeSearch.query}
              onChange={(event) => activeSearch.change(event.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder={
                searchMode === 'location'
                  ? 'Search a street, landmark, neighbourhood or city'
                  : 'Search a username or display name'
              }
              className="min-w-0 flex-1 bg-transparent text-sm font-medium text-ink-900 outline-none placeholder:text-ink-400"
            />
            {activeSearch.query && (
              <button
                type="button"
                aria-label={searchMode === 'location' ? 'Clear location search' : 'Clear people search'}
                onClick={searchMode === 'location' ? clearLocationSearch : peopleSearch.clear}
                className="flex size-8 shrink-0 items-center justify-center rounded-full text-ink-400 hover:bg-ink-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            )}
            <Button
              type="submit"
              size="icon"
              aria-label="Search"
              className="size-9 shrink-0 rounded-full"
              disabled={activeSearch.searching}
            >
              <Search className="size-4" aria-hidden="true" />
            </Button>
          </form>

          {activeSearch.isOpen && (
            <div className="mt-2 max-h-64 overflow-y-auto rounded-2xl border border-ink-100 bg-white p-1 shadow-float">
              {activeSearch.searching && (
                <p className="px-3 py-2 text-sm text-ink-500" role="status">
                  Searching…
                </p>
              )}
              {activeSearch.error && (
                <p className="px-3 py-2 text-sm text-ink-500" role="status">
                  {activeSearch.error}
                </p>
              )}
              <ul
                id={listboxId}
                role="listbox"
                aria-label={searchMode === 'location' ? 'Location suggestions' : 'Profile suggestions'}
              >
                {searchMode === 'location'
                  ? search.results.map((result, index) => (
                      <li
                        key={`${result.latitude}-${result.longitude}`}
                        id={`${listboxId}-${index}`}
                        role="option"
                        aria-selected={index === search.activeIndex}
                        onMouseEnter={() => search.setActiveIndex(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectLocation(result)}
                        className={`cursor-pointer rounded-xl px-3 py-2 ${
                          index === search.activeIndex ? 'bg-ink-50' : ''
                        }`}
                      >
                        <span className="block text-sm font-semibold text-ink-900">{result.area}</span>
                        <span className="block truncate text-xs text-ink-500">{result.name}</span>
                      </li>
                    ))
                  : peopleSearch.results.map((profile, index) => (
                      <li
                        key={profile.id}
                        id={`${listboxId}-${index}`}
                        role="option"
                        aria-selected={index === peopleSearch.activeIndex}
                        onMouseEnter={() => peopleSearch.setActiveIndex(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectProfile(profile)}
                        className={`flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 ${
                          index === peopleSearch.activeIndex ? 'bg-ink-50' : ''
                        }`}
                      >
                        <Avatar name={profile.displayName} src={profile.photo ?? undefined} size="sm" />
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold text-ink-900">
                            {profile.displayName}
                          </span>
                          <span className="block truncate text-xs text-ink-500">@{profile.username}</span>
                        </span>
                      </li>
                    ))}
              </ul>
            </div>
          )}
        </div>

        {googleMapsReady ? (
          <GoogleMapView
            profiles={items}
            highlightedId={items[0]?.id}
            center={mapCenterProp}
            locationLabel={activeMapLocationLabel}
            userLocation={userLocation}
            distanceExpanded={data?.distanceExpanded}
          />
        ) : (
          <div className="flex size-full items-center justify-center bg-ink-100 p-6 text-center">
            <p className="max-w-sm text-sm font-medium text-ink-600" role="status">
              Google Maps is not configured for this environment.
            </p>
          </div>
        )}

        {isLoading && cursor === 0 && (
          <div className="absolute inset-0 z-[1100] bg-white/70" role="status" aria-label="Loading nearby profiles">
            <span className="sr-only">Loading nearby profiles</span>
            <Skeleton className="absolute left-[18%] top-[32%] size-11 rounded-full" />
            <Skeleton className="absolute left-[62%] top-[44%] size-11 rounded-full" />
            <Skeleton className="absolute left-[38%] top-[68%] size-11 rounded-full" />
          </div>
        )}

        {isError && (
          <div className="absolute inset-0 z-[1100] flex items-center justify-center bg-white/80 p-6">
            <ErrorState title="Couldn't load profiles" action={{ label: 'Retry', onClick: () => refetch() }} />
          </div>
        )}

        {showEmpty && (
          <div className="absolute inset-0 z-[1100] flex items-center justify-center bg-white/80 p-6">
            <EmptyState
              title={filters.interests.length > 0 ? 'No profiles match these interests' : 'No matches yet'}
              description={
                filters.interests.length > 0
                  ? 'Clear the interest filters to see everyone who fits your other preferences.'
                  : 'Widen the age or distance range, switch Show me to Everyone, or reset your filters.'
              }
              action={
                filters.interests.length > 0
                  ? { label: 'Clear interest filters', onClick: clearInterestFilters }
                  : { label: 'Reset all filters', onClick: resetAll }
              }
            />
          </div>
        )}
      </div>

      {/* Results */}
      {(items.length > 0 || isLoading) && (
        <section className="mt-6" aria-labelledby="discover-results-heading">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="discover-results-heading" className="min-w-0 truncate text-base font-semibold text-ink-900">
              {heading}
            </h2>
            {items.length > 0 && (
              <span className="shrink-0 text-sm text-ink-500">
                {items.length} {items.length === 1 ? 'person' : 'people'}
              </span>
            )}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {items.map((profile) => (
              <CircleCard key={profile.id} profile={profile} showDistance={locationEnabled} />
            ))}
            {isLoading &&
              Array.from({ length: 6 }, (_, index) => <DiscoveryCardSkeleton key={`loading-${index}`} />)}
          </div>
        </section>
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
          focusSearch()
        }}
      />
      <LocationAccessDialog
        open={shareDialogOpen}
        locating={share.busy}
        message={share.message}
        title="Share your current location?"
        description="People who discover profiles around your area can find you while sharing is on."
        privacyMessage="Your exact coordinates are never shown. Others see an approximate area and distance. Sharing stops when you turn it off or location updates expire after 5 minutes."
        actionLabel="Start sharing"
        onClose={() => setShareDialogOpen(false)}
        onAllow={() => void enableLocationSharing()}
        onChooseManually={() => {
          setShareDialogOpen(false)
          share.setMessage(null)
        }}
      />
    </div>
  )
}