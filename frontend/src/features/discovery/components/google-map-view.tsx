import { useLayoutEffect } from 'react'
import { Link } from 'react-router-dom'
import { APIProvider, AdvancedMarker, Map, useAdvancedMarkerRef } from '@vis.gl/react-google-maps'
import { cn } from '@/lib/utils'
import type { MemberProfile } from '@/lib/api/types'
import { DISCOVERY_MAP_ZOOM, geoPosition, LAGOS_CENTER } from './map-utils'

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
const GOOGLE_MAPS_MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string | undefined

export function isGoogleMapsConfigured() {
  if (!GOOGLE_MAPS_API_KEY) return false
  const key = GOOGLE_MAPS_API_KEY.trim()
  if (key.length < 20) return false
  if (/^(your[_ -]?google|google[_ -]?api[_ -]?key|required|api[_ -]?key)$/i.test(key)) return false
  return true
}

function GoogleProfileMarker({
  profile,
  highlighted,
  locationLabel,
}: {
  profile: MemberProfile
  highlighted: boolean
  locationLabel?: string
}) {
  const [markerRef, marker] = useAdvancedMarkerRef()
  const position = geoPosition(profile)
  if (!position) return null

  return (
    <AdvancedMarker ref={markerRef} position={position} clickable>
      <>
        <DetachMarkerBeforeContentRemoval marker={marker} />
        <Link
          to={`/profiles/${profile.id}`}
          aria-label={`View ${profile.displayName}'s profile`}
          className="relative block -translate-y-1/2 cursor-pointer select-none"
        >
          <span
            className={cn(
              'absolute left-1/2 top-full -mt-1 h-2.5 -translate-x-1/2 rounded-full blur-[2px]',
              highlighted ? 'w-10 bg-primary-500/35' : 'w-7 bg-ink-900/20',
            )}
          />
          <div className="flex flex-col items-center">
            {profile.photos[0] ? (
              <img
                src={profile.photos[0]}
                alt=""
                className={cn(
                  'rounded-full border-4 object-cover shadow-float',
                  highlighted ? 'size-14 border-primary-500' : 'size-12 border-white',
                )}
              />
            ) : (
              <span
                aria-hidden="true"
                className={cn(
                  'flex items-center justify-center rounded-full border-4 bg-primary-100 font-semibold text-primary-700 shadow-float',
                  highlighted ? 'size-14 border-primary-500' : 'size-12 border-white',
                )}
              >
                {profile.displayName.slice(0, 1).toUpperCase()}
              </span>
            )}
            <div className="mt-1 max-w-32 rounded-xl border border-white/80 bg-white/95 px-2.5 py-1 text-center shadow-float backdrop-blur-sm">
              <p className="truncate text-xs font-bold leading-tight text-ink-900">{profile.displayName}</p>
              <p className="truncate text-[10px] leading-tight text-ink-500">{locationLabel || profile.area}</p>
            </div>
          </div>
        </Link>
      </>
    </AdvancedMarker>
  )
}

function DetachMarkerBeforeContentRemoval({
  marker,
}: {
  marker: ReturnType<typeof useAdvancedMarkerRef>[1]
}) {
  useLayoutEffect(() => {
    if (!marker) return

    return () => {
      marker.map = null
    }
  }, [marker])

  return null
}

export function GoogleMapView({
  profiles,
  highlightedId,
  center,
  zoom = DISCOVERY_MAP_ZOOM,
  locationLabel,
  userLocation,
  distanceExpanded = false,
}: {
  profiles: MemberProfile[]
  highlightedId?: string
  center?: { lat: number; lng: number }
  zoom?: number
  locationLabel?: string
  userLocation?: { latitude: number; longitude: number } | null
  distanceExpanded?: boolean
}) {
  if (!GOOGLE_MAPS_API_KEY) return null

  const mapCenter = center ?? LAGOS_CENTER
  const hasUnmappedProfiles = profiles.some((profile) => geoPosition(profile) === null)

  return (
    <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
      <div
        className="relative size-full"
        role="region"
        aria-label="Read-only map showing approximate member locations. Select an avatar to open a profile."
      >
        <Map
          mapId={GOOGLE_MAPS_MAP_ID}
          center={mapCenter}
          zoom={distanceExpanded ? 1 : zoom}
          defaultTilt={0}
          defaultHeading={0}
          gestureHandling="none"
          draggable={false}
          keyboardShortcuts={false}
          disableDoubleClickZoom
          scrollwheel={false}
          mapTypeId="roadmap"
          disableDefaultUI
          className="size-full"
        >
          {userLocation && (
            <AdvancedMarker position={{ lat: userLocation.latitude, lng: userLocation.longitude }} title="Your location">
              <span className="relative flex size-5 items-center justify-center" aria-hidden="true">
                <span className="absolute size-5 animate-ping rounded-full bg-primary-500/30" />
                <span className="relative size-3 rounded-full border-2 border-white bg-primary-600 shadow-float" />
              </span>
            </AdvancedMarker>
          )}
          {profiles.map((profile) => (
            <GoogleProfileMarker
              key={profile.id}
              profile={profile}
              highlighted={profile.id === highlightedId}
              locationLabel={locationLabel}
            />
          ))}
        </Map>
        {hasUnmappedProfiles && (
          <p className="pointer-events-none absolute bottom-3 left-3 z-10 rounded-full border border-ink-100 bg-white/90 px-3 py-1.5 text-xs font-medium text-ink-600 shadow-sm">
            Some profiles aren’t pinned because they don’t have location coordinates.
          </p>
        )}
      </div>
    </APIProvider>
  )
}
