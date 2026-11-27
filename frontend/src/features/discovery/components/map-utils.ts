import type { MemberProfile } from '@/lib/api/types'

export const LAGOS_CENTER = { lat: 6.4698, lng: 3.5852 }
export const DISCOVERY_MAP_ZOOM = 16

export function geoPosition(
  profile: MemberProfile,
): { lat: number; lng: number } | null {
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
  return null
}
