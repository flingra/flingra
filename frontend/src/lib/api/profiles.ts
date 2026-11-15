import { apiRequest, delay, ensureCsrfHeaders, uploadFile } from './client'
import { ownProfileStore, PROFILES } from './mock-db'
import { getPresence } from './presence'
import {
  ApiError,
  type DiscoveryFilters,
  type MemberProfile,
  type OwnProfile,
  type PagedResult,
  type VerificationDocumentType,
} from './types'

const PAGE_SIZE = 6

export const DEFAULT_FILTERS: DiscoveryFilters = {
  minAge: 20,
  maxAge: 45,
  maxDistanceKm: 25,
  interests: [],
  liveOnly: false,
  lookingFor: 'everyone',
}

/**
 * VIP members match each other regardless of distance — a mutual soft spot that
 * waives the normal `maxDistanceKm` filter when both the viewer and the candidate
 * are subscribed.
 */
function matchesFilters(profile: MemberProfile, filters: DiscoveryFilters, viewerIsVip: boolean) {
  const [minAge] = profile.ageRange.split('–').map(Number)
  if (minAge < filters.minAge || minAge > filters.maxAge) return false
  const distanceWaived = viewerIsVip && profile.subscriptionTier === 'vip'
  if (!distanceWaived && profile.distanceKm > filters.maxDistanceKm) return false
  if (filters.lookingFor !== 'everyone') {
    const wanted = filters.lookingFor === 'men' ? 'man' : 'woman'
    if (profile.identity !== wanted) return false
  }
  if (filters.interests.length > 0 && !profile.interests.some((interest) => filters.interests.includes(interest))) {
    return false
  }
  if (filters.liveOnly && !getPresence(profile.id).isLive) return false
  return true
}

export async function getDiscoveryFeed(
  filters: DiscoveryFilters,
  cursor = 0,
): Promise<PagedResult<MemberProfile>> {
  await delay(null, 650)
  const viewerIsVip = ownProfileStore.profile?.subscriptionTier === 'vip'
  const eligible = PROFILES.filter((profile) => profile.id !== 'me' && matchesFilters(profile, filters, viewerIsVip))
  const items = eligible.slice(cursor, cursor + PAGE_SIZE)
  const nextCursor = cursor + PAGE_SIZE < eligible.length ? cursor + PAGE_SIZE : null
  return { items, nextCursor }
}

export async function getProfile(id: string): Promise<MemberProfile> {
  await delay(null, 450)
  const profile = PROFILES.find((item) => item.id === id)
  if (!profile) {
    throw new ApiError('PROFILE_NOT_FOUND', 'This profile is unavailable. It may have been removed.')
  }
  return profile
}

export async function getOwnProfile(): Promise<OwnProfile> {
  return apiRequest<OwnProfile>('/profiles/me')
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
  await uploadPhoto(file)
  await saveOwnProfile({ documentType, documentVerification: 'pending' })
}

export async function uploadVideo(file: File): Promise<string> {
  await delay(null, 1200)
  return URL.createObjectURL(file)
}

export interface NearbyVideo {
  authorId: string
  authorName: string
  authorPhoto: string
  video: string
}

/** Every VIP member, for the VIP showcase page — visible to everyone, interaction gated elsewhere. */
export async function listVipProfiles(): Promise<MemberProfile[]> {
  await delay(null, 500)
  return PROFILES.filter((profile) => profile.id !== 'me' && profile.subscriptionTier === 'vip')
}

/** Only free (unlocked) videos appear in this teaser feed — paid content only shows on the profile itself. */
export async function listNearbyVideos(): Promise<NearbyVideo[]> {
  await delay(null, 400)
  return PROFILES.filter((profile) => profile.id !== 'me' && profile.videos && profile.videos.length > 0).flatMap((profile) =>
    (profile.videos ?? [])
      .filter((video) => !video.locked)
      .map((video) => ({
        authorId: profile.id,
        authorName: profile.displayName,
        authorPhoto: profile.photos[0],
        video: video.url,
      })),
  )
}
