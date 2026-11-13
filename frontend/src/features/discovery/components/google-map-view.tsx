import { APIProvider, AdvancedMarker, Map } from '@vis.gl/react-google-maps'
import { cn } from '@/lib/utils'
import type { MemberProfile } from '@/lib/api/types'

// Flingra is Nigeria-first; Lekki, Lagos is a reasonable default map centre for the mock feed.
const LAGOS_CENTER = { lat: 6.4698, lng: 3.5852 }

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
const GOOGLE_MAPS_MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string | undefined

export function isGoogleMapsConfigured() {
  return Boolean(GOOGLE_MAPS_API_KEY)
}

/** Deterministic fake coordinates near the centre so the same profile always lands in the same spot. */
function fnv1a(str: string) {
  let hash = 0x811c9dc5
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

function geoPosition(id: string) {
  const hash = fnv1a(id)
  const latOffset = (((hash >>> 16) % 1000) / 1000 - 0.5) * 0.03
  const lngOffset = (((hash & 0xffff) % 1000) / 1000 - 0.5) * 0.03
  return { lat: LAGOS_CENTER.lat + latOffset, lng: LAGOS_CENTER.lng + lngOffset }
}

export function GoogleMapView({
  profiles,
  highlightedId,
}: {
  profiles: MemberProfile[]
  highlightedId?: string
}) {
  if (!GOOGLE_MAPS_API_KEY) return null

  return (
    <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
      <Map
        mapId={GOOGLE_MAPS_MAP_ID}
        defaultCenter={LAGOS_CENTER}
        defaultZoom={15}
        defaultTilt={45}
        defaultHeading={20}
        gestureHandling="greedy"
        className="size-full"
      >
        {profiles.map((profile) => {
          const highlighted = profile.id === highlightedId
          return (
            <AdvancedMarker key={profile.id} position={geoPosition(profile.id)}>
              <div className="relative -translate-y-1/2">
                <span
                  className={cn(
                    'absolute left-1/2 top-full -mt-1 h-2.5 -translate-x-1/2 rounded-full blur-[2px]',
                    highlighted ? 'w-10 bg-primary-500/35' : 'w-7 bg-ink-900/20',
                  )}
                />
                <img
                  src={profile.photos[0]}
                  alt=""
                  className={cn(
                    'rounded-full border-4 object-cover shadow-float',
                    highlighted ? 'size-14 border-primary-500' : 'size-12 border-white',
                  )}
                />
              </div>
            </AdvancedMarker>
          )
        })}
      </Map>
    </APIProvider>
  )
}
