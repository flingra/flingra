import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
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

function geoPosition(id: string, center: { lat: number; lng: number } = LAGOS_CENTER) {
  const hash = fnv1a(id)
  const latOffset = (((hash >>> 16) % 1000) / 1000 - 0.5) * 0.03
  const lngOffset = (((hash & 0xffff) % 1000) / 1000 - 0.5) * 0.03
  return { lat: center.lat + latOffset, lng: center.lng + lngOffset }
}

export function OpenStreetMapView({
  profiles = [],
  highlightedId,
  useMyLocation = false,
  center,
  zoom = 15,
  onLocationSelect,
}: {
  profiles?: MemberProfile[]
  highlightedId?: string
  useMyLocation?: boolean
  center?: [number, number]
  zoom?: number
  onLocationSelect?: (latitude: number, longitude: number) => void
}) {
  const mapContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!mapContainerRef.current) return

    const map = L.map(mapContainerRef.current, {
      center: center ?? [LAGOS_CENTER.lat, LAGOS_CENTER.lng],
      zoom,
      zoomControl: false,
      scrollWheelZoom: false,
      dragging: false,
      touchZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      maxZoom: 19,
    }).addTo(map)

    if (onLocationSelect) {
      map.on('click', (event: L.LeafletMouseEvent) => {
        onLocationSelect(event.latlng.lat, event.latlng.lng)
      })
    }

    const markerLayer = L.layerGroup().addTo(map)

    profiles.forEach((profile) => {
      const highlighted = profile.id === highlightedId
      const marker = L.marker(geoPosition(profile.id, center ? { lat: center[0], lng: center[1] } : LAGOS_CENTER), {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: 'profile-map-marker',
          html: '<div class="profile-map-marker-inner"><img alt="" /></div>',
          iconSize: highlighted ? [56, 56] : [48, 48],
          iconAnchor: highlighted ? [28, 28] : [24, 24],
        }),
      })

      marker.addTo(markerLayer)
      const element = marker.getElement()
      const image = element?.querySelector('img')
      if (image) {
        image.src = profile.photos[0] ?? ''
        image.className = highlighted
          ? 'size-14 rounded-full border-4 border-primary-500 object-cover shadow-float'
          : 'size-12 rounded-full border-4 border-white object-cover shadow-float'
      }
    })

    let locationMarker: L.CircleMarker | undefined
    if (useMyLocation && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          const position: L.LatLngExpression = [coords.latitude, coords.longitude]
          map.setView(position, 15)
          locationMarker = L.circleMarker(position, {
            radius: 8,
            color: '#ffffff',
            fillColor: '#4f46e5',
            fillOpacity: 1,
            weight: 3,
          }).addTo(map)
        },
        () => undefined,
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 300000 },
      )
    }

    window.requestAnimationFrame(() => map.invalidateSize())

    return () => {
      locationMarker?.remove()
      map.remove()
    }
  }, [profiles, highlightedId, useMyLocation, center, zoom, onLocationSelect])

  return <div ref={mapContainerRef} className="size-full bg-ink-100" aria-label="Discover members map" />
}

export function GoogleMapView({
  profiles,
  highlightedId,
  center = LAGOS_CENTER,
}: {
  profiles: MemberProfile[]
  highlightedId?: string
  center?: { lat: number; lng: number }
}) {
  if (!GOOGLE_MAPS_API_KEY) return null

  return (
    <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
      <Map
        mapId={GOOGLE_MAPS_MAP_ID}
        center={center}
        zoom={15}
        defaultTilt={45}
        defaultHeading={20}
        gestureHandling="none"
        disableDefaultUI
        className="size-full"
      >
        {profiles.map((profile) => {
          const highlighted = profile.id === highlightedId
          return (
            <AdvancedMarker key={profile.id} position={geoPosition(profile.id, center)}>
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
