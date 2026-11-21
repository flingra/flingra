import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import * as L from 'leaflet'
import { APIProvider, Map, Marker } from '@vis.gl/react-google-maps'
import type { MemberProfile } from '@/lib/api/types'

// Flingra is Nigeria-first; Lekki, Lagos is a reasonable default map centre for the mock feed.
const LAGOS_CENTER = { lat: 6.4698, lng: 3.5852 }

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
const GOOGLE_MAPS_MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string | undefined

export function isGoogleMapsConfigured() {
  if (!GOOGLE_MAPS_API_KEY) return false
  const key = GOOGLE_MAPS_API_KEY.trim()
  if (key.length < 20) return false
  if (/^(your[_ -]?google|google[_ -]?api[_ -]?key|required|api[_ -]?key)$/i.test(key)) return false
  return true
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

function geoPosition(profile: MemberProfile, center: { lat: number; lng: number } = LAGOS_CENTER) {
  const base = center
  const hash = fnv1a(profile.id)
  const latOffset = (((hash >>> 16) % 1000) / 1000 - 0.5) * 0.018
  const lngOffset = (((hash & 0xffff) % 1000) / 1000 - 0.5) * 0.018
  return { lat: base.lat + latOffset, lng: base.lng + lngOffset }
}

export function OpenStreetMapView({
  profiles = [],
  highlightedId,
  useMyLocation = false,
  center,
  zoom = 15,
  onLocationSelect,
  locationLabel,
}: {
  profiles?: MemberProfile[]
  highlightedId?: string
  useMyLocation?: boolean
  center?: [number, number]
  zoom?: number
  onLocationSelect?: (latitude: number, longitude: number) => void
  locationLabel?: string
}) {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

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

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
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
      const marker = L.marker(geoPosition(profile, center ? { lat: center[0], lng: center[1] } : LAGOS_CENTER), {
        interactive: true,
        keyboard: true,
        icon: L.divIcon({
          className: 'profile-map-marker',
          html: `<div class="profile-map-marker-inner"><img alt="" /><span class="profile-map-marker-label"><strong>${profile.displayName}</strong><small>${locationLabel || profile.area}</small></span></div>`,
          iconSize: highlighted ? [132, 76] : [124, 68],
          iconAnchor: highlighted ? [66, 76] : [62, 68],
        }),
      })

      marker.on('click', () => navigate(`/profiles/${profile.id}`))
      marker.on('keydown', (event: L.LeafletKeyboardEvent) => {
        if (event.originalEvent.key === 'Enter' || event.originalEvent.key === ' ') {
          event.originalEvent.preventDefault()
          navigate(`/profiles/${profile.id}`)
        }
      })
      marker.addTo(markerLayer)
      const element = marker.getElement()
      if (element) {
        element.setAttribute('role', 'link')
        element.setAttribute('tabindex', '0')
        element.setAttribute('aria-label', `View ${profile.displayName}'s profile`)
      }
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
  }, [profiles, highlightedId, useMyLocation, center, zoom, onLocationSelect, locationLabel, navigate])

  return <div ref={mapContainerRef} className="size-full bg-ink-100" aria-label="Discover members map" />
}

function GoogleProfileMarker({
  profile,
  highlighted,
  center,
  locationLabel,
}: {
  profile: MemberProfile
  highlighted: boolean
  center: { lat: number; lng: number }
  locationLabel?: string
}) {
  const navigate = useNavigate()

  return (
    <Marker
      position={geoPosition(profile, center)}
      title={`${profile.displayName} — ${locationLabel || profile.area}`}
      label={{
        text: profile.displayName,
        color: '#15120f',
        fontSize: highlighted ? '13px' : '11px',
        fontWeight: '600',
      }}
      onClick={() => navigate(`/profiles/${profile.id}`)}
    />
  )
}

export function GoogleMapView({
  profiles,
  highlightedId,
  center = LAGOS_CENTER,
  locationLabel,
}: {
  profiles: MemberProfile[]
  highlightedId?: string
  center?: { lat: number; lng: number }
  locationLabel?: string
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
        {profiles.map((profile) => (
          <GoogleProfileMarker
            key={profile.id}
            profile={profile}
            highlighted={profile.id === highlightedId}
            center={center}
            locationLabel={locationLabel}
          />
        ))}
      </Map>
    </APIProvider>
  )
}
