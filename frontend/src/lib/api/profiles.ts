import { apiRequest, ensureCsrfHeaders, resolveMediaUrl, uploadFile } from './client'
import {
  type DiscoveryFilters,
  type MemberProfile,
  type OwnProfile,
  type PagedResult,
  type ProfileVideo,
  type VerificationDocumentType,
} from './types'

export const DEFAULT_FILTERS: DiscoveryFilters = {
  minAge: 21,
  maxAge: 45,
  maxDistanceKm: 25,
  interests: [],
  liveOnly: false,
  lookingFor: 'everyone',
}

function resolveProfileMedia(profile: MemberProfile): MemberProfile {
  return {
    ...profile,
    photos: profile.photos.map(resolveMediaUrl),
    videos: profile.videos?.map((video: ProfileVideo) => ({
      ...video,
      url: resolveMediaUrl(video.url),
    })),
  }
}

export async function getDiscoveryFeed(
  filters: DiscoveryFilters,
  cursor = 0,
  origin?: { latitude: number; longitude: number },
  distanceEnabled = false,
): Promise<PagedResult<MemberProfile>> {
  const params = new URLSearchParams({
    minAge: String(filters.minAge),
    maxAge: String(filters.maxAge),
    lookingFor: filters.lookingFor,
    liveOnly: String(filters.liveOnly),
    cursor: String(cursor),
  })
  if (distanceEnabled) params.set('maxDistanceKm', String(filters.maxDistanceKm))
  if (origin) {
    params.set('latitude', String(origin.latitude))
    params.set('longitude', String(origin.longitude))
  }
  filters.interests.forEach((interest) => params.append('interests', interest))

  const result = await apiRequest<PagedResult<MemberProfile>>(`/discovery?${params.toString()}`)
  return { ...result, items: result.items.map(resolveProfileMedia) }
}

export async function getDiscoverableProfile(id: string): Promise<MemberProfile> {
  const profile = await apiRequest<MemberProfile>(`/profiles/${encodeURIComponent(id)}`)
  return resolveProfileMedia(profile)
}

export async function getProfile(id: string): Promise<MemberProfile> {
  return getDiscoverableProfile(id)
}

export async function getOwnProfile(): Promise<OwnProfile> {
  return apiRequest<OwnProfile>('/profiles/me')
}

export async function publishCurrentLocation(location: { latitude: number; longitude: number }): Promise<void> {
  await apiRequest('/profiles/me/location-sharing', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify(location),
  })
}

export async function stopLocationSharing(): Promise<void> {
  await apiRequest('/profiles/me/location-sharing', {
    method: 'DELETE',
    headers: await ensureCsrfHeaders(),
  })
}

export async function saveOwnProfile(partial: Partial<OwnProfile>): Promise<OwnProfile> {
  const payload = {
    ...(partial.displayName !== undefined ? { displayName: partial.displayName } : {}),
    ...(partial.bio !== undefined ? { bio: partial.bio } : {}),
    ...(partial.photos !== undefined ? { photos: partial.photos } : {}),
    ...(partial.videos !== undefined ? { videos: partial.videos } : {}),
    ...(partial.area !== undefined ? { area: partial.area } : {}),
    ...(partial.latitude !== undefined ? { latitude: partial.latitude } : {}),
    ...(partial.longitude !== undefined ? { longitude: partial.longitude } : {}),
    ...(partial.interests !== undefined ? { interests: partial.interests } : {}),
    ...(partial.discoverableBy !== undefined ? { discoverableBy: partial.discoverableBy } : {}),
    ...(partial.wantsToDiscover !== undefined ? { wantsToDiscover: partial.wantsToDiscover } : {}),
    ...(partial.identity !== undefined ? { identity: partial.identity } : {}),
    ...(partial.showIdentity !== undefined ? { showIdentity: partial.showIdentity } : {}),
    ...(partial.twoFactorEnabled !== undefined ? { twoFactorEnabled: partial.twoFactorEnabled } : {}),
    ...(partial.twoFactorMethod !== undefined ? { twoFactorMethod: partial.twoFactorMethod } : {}),
  }
  return apiRequest<OwnProfile>('/profiles/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify(payload),
  })
}

export async function uploadPhoto(file: File): Promise<string> {
  const result = await uploadFile<{ url: string }>('/media/photos', file)
  return result.url
}

export async function uploadIdentityDocument(
  file: File,
  documentType: VerificationDocumentType,
): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('documentType', documentType)
  await apiRequest<void>('/media/documents', {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
    body: formData,
  })
}

export async function uploadVideo(file: File): Promise<string> {
  const result = await apiRequest<{ url: string }>(`/media/videos?purpose=profile`, {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
    body: (() => {
      const form = new FormData()
      form.append('file', file)
      return form
    })(),
  })
  return result.url
}

export interface NearbyVideo {
  authorId: string
  authorName: string
  authorPhoto: string
  video: string
}

/** Every VIP member, for the VIP showcase page — visible to everyone, interaction gated elsewhere. */
export async function listVipProfiles(): Promise<MemberProfile[]> {
  const profiles = await apiRequest<MemberProfile[]>('/profiles')
  return profiles.map(resolveProfileMedia)
}

/** Only free (unlocked) videos appear in this teaser feed — paid content only shows on the profile itself. */
export async function listNearbyVideos(): Promise<NearbyVideo[]> {
  return apiRequest<NearbyVideo[]>('/videos/nearby')
}
