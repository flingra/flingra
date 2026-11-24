import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
import type { MemberProfile } from '@/lib/api/types'
import { DISCOVERY_MAP_ZOOM, geoPosition, LAGOS_CENTER } from './map-utils'

export function OpenStreetMapView({
  profiles = [],
  highlightedId,
  useMyLocation = false,
  center,
  zoom = DISCOVERY_MAP_ZOOM,
  userLocation,
  locationLabel,
}: {
  profiles?: MemberProfile[]
  highlightedId?: string
  useMyLocation?: boolean
  center?: [number, number]
  zoom?: number
  userLocation?: { latitude: number; longitude: number }
  locationLabel?: string
}) {
  const mapContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!mapContainerRef.current) return

    const map = L.map(mapContainerRef.current, {
      center: userLocation
        ? [userLocation.latitude, userLocation.longitude]
        : center ?? [LAGOS_CENTER.lat, LAGOS_CENTER.lng],
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
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
      maxZoom: 19,
    }).addTo(map)

    const markerLayer = L.layerGroup().addTo(map)

    profiles.forEach((profile) => {
      const highlighted = profile.id === highlightedId
      const marker = L.marker(
        geoPosition(profile, center ? { lat: center[0], lng: center[1] } : LAGOS_CENTER),
        {
          interactive: false,
          keyboard: false,
          icon: L.divIcon({
            className: 'profile-map-marker',
            html: `<div class="profile-map-marker-inner"><img alt="" /><span class="profile-map-marker-label"><strong>${profile.displayName}</strong><small>${locationLabel || profile.area}</small></span></div>`,
            iconSize: highlighted ? [132, 76] : [124, 68],
            iconAnchor: highlighted ? [66, 76] : [62, 68],
          }),
        },
      )

      marker.addTo(markerLayer)
      const element = marker.getElement()
      if (element) {
        element.setAttribute('aria-hidden', 'true')
      }
      const image = element?.querySelector('img')
      if (image) {
        image.src = profile.photos[0] ?? ''
        image.className = highlighted
          ? 'size-14 rounded-full border-4 border-primary-500 object-cover shadow-float'
          : 'size-12 rounded-full border-4 border-white object-cover shadow-float'
      }
    })

    const userLocationMarker = userLocation
      ? L.circleMarker([userLocation.latitude, userLocation.longitude], {
          radius: 8,
          color: '#ffffff',
          fillColor: '#4f46e5',
          fillOpacity: 1,
          weight: 3,
        }).addTo(map)
      : undefined

    let locationMarker: L.CircleMarker | undefined
    if (useMyLocation && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          const position: L.LatLngExpression = [coords.latitude, coords.longitude]
          map.setView(position, DISCOVERY_MAP_ZOOM)
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
      userLocationMarker?.remove()
      locationMarker?.remove()
      map.remove()
    }
  }, [profiles, highlightedId, useMyLocation, center, zoom, userLocation, locationLabel])

  return <div ref={mapContainerRef} className="size-full bg-ink-100" role="img" aria-label="" />
}
