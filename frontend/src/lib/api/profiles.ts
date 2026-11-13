import { delay } from './client'
import { ownProfileStore, PROFILES } from './mock-db'
import { ApiError, type DiscoveryFilters, type MemberProfile, type OwnProfile, type PagedResult } from './types'

const PAGE_SIZE = 6

export const DEFAULT_FILTERS: DiscoveryFilters = { minAge: 20, maxAge: 45, maxDistanceKm: 25 }

function matchesFilters(profile: MemberProfile, filters: DiscoveryFilters) {
  const [minAge] = profile.ageRange.split('–').map(Number)
  return minAge >= filters.minAge && minAge <= filters.maxAge && profile.distanceKm <= filters.maxDistanceKm
}

export async function getDiscoveryFeed(
  filters: DiscoveryFilters,
  cursor = 0,
): Promise<PagedResult<MemberProfile>> {
  await delay(null, 650)
  const eligible = PROFILES.filter((profile) => profile.id !== 'me' && matchesFilters(profile, filters))
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
  await delay(null, 400)
  if (!ownProfileStore.profile) {
    throw new ApiError('NO_PROFILE', 'Finish onboarding to create your profile.')
  }
  return ownProfileStore.profile
}

export async function saveOwnProfile(partial: Partial<OwnProfile>): Promise<OwnProfile> {
  await delay(null, 700)
  const existing = ownProfileStore.profile ?? {
    id: 'me',
    displayName: '',
    bio: '',
    photos: [],
    ageRange: '25–30',
    area: '',
    distanceKm: 0,
    interests: [],
    discoverableBy: 'everyone' as const,
    wantsToDiscover: 'everyone' as const,
    identity: 'private' as const,
    showIdentity: false,
    moderationStatus: 'pending' as const,
  }
  ownProfileStore.profile = { ...existing, ...partial }
  return ownProfileStore.profile
}

export async function uploadPhoto(file: File): Promise<string> {
  await delay(null, 900)
  return URL.createObjectURL(file)
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

export async function listNearbyVideos(): Promise<NearbyVideo[]> {
  await delay(null, 400)
  return PROFILES.filter((profile) => profile.id !== 'me' && profile.videos && profile.videos.length > 0).flatMap((profile) =>
    (profile.videos ?? []).map((video) => ({
      authorId: profile.id,
      authorName: profile.displayName,
      authorPhoto: profile.photos[0],
      video,
    })),
  )
}
