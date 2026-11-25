import type { MemberProfile } from '@/lib/api/types'

export const LAGOS_CENTER = { lat: 6.4698, lng: 3.5852 }
export const DISCOVERY_MAP_ZOOM = 16
const PROFILE_MARKER_SPREAD = 0.008

function fnv1a(value: string) {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

export function geoPosition(
  profile: MemberProfile,
  center: { lat: number; lng: number } = LAGOS_CENTER,
) {
  if (
    profile.latitude != null &&
    profile.longitude != null &&
    Number.isFinite(profile.latitude) &&
    Number.isFinite(profile.longitude) &&
    Math.abs(profile.latitude) <= 90 &&
    Math.abs(profile.longitude) <= 180
  ) {
    return { lat: profile.latitude, lng: profile.longitude }
  }
  const hash = fnv1a(profile.id)
  const latOffset = (((hash >>> 16) % 1000) / 1000 - 0.5) * PROFILE_MARKER_SPREAD
  const lngOffset = (((hash & 0xffff) % 1000) / 1000 - 0.5) * PROFILE_MARKER_SPREAD
  return { lat: center.lat + latOffset, lng: center.lng + lngOffset }
}
