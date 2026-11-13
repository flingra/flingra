export type AudiencePreference = 'men' | 'women' | 'everyone'

export type AccountStage = 'needs-verification' | 'needs-onboarding' | 'active'

export interface Session {
  accountId: string
  maskedContact: string
  stage: AccountStage
}

export interface MemberProfile {
  id: string
  displayName: string
  bio: string
  photos: string[]
  videos?: string[]
  ageRange: string
  area: string
  distanceKm: number
  interests: string[]
  discoverableBy: AudiencePreference
  wantsToDiscover: AudiencePreference
  identity: 'man' | 'woman' | 'private'
  showIdentity: boolean
}

export interface OwnProfile extends MemberProfile {
  moderationStatus: 'approved' | 'pending' | 'rejected'
}

export interface DiscoveryFilters {
  minAge: number
  maxAge: number
  maxDistanceKm: number
}

export interface PagedResult<T> {
  items: T[]
  nextCursor: number | null
}

export interface BlockedAccount {
  id: string
  displayName: string
  photo: string | null
  blockedAt: string
}

export type ReportReason = 'fake-profile' | 'harassment' | 'inappropriate-content' | 'underage' | 'other'

export interface Post {
  id: string
  authorId: string
  photos: string[]
  video?: string
  caption?: string
  createdAt: string
}

export interface Status {
  id: string
  authorId: string
  authorName: string
  authorPhoto: string
  media: string
  kind: 'image' | 'video'
  createdAt: string
}

export interface LiveStream {
  id: string
  hostId: string
  hostName: string
  hostPhoto: string
  hostVideo?: string
  title: string
  startedAt: string
  participantIds: string[]
}

export interface JoinRequest {
  id: string
  streamId: string
  requesterId: string
  requesterName: string
  requesterPhoto: string
}

export interface StreamMessage {
  id: string
  streamId: string
  authorId: string
  authorName: string
  kind: 'message' | 'gift' | 'join'
  text: string
  giftId?: string
  createdAt: string
}

export interface GiftType {
  id: string
  name: string
  emoji: string
  priceNaira: number
}

export interface OwnedGift {
  giftTypeId: string
  quantity: number
}

export interface ReceivedGift {
  id: string
  giftTypeId: string
  fromId: string
  fromName: string
  valueNaira: number
  redeemed: boolean
  createdAt: string
}

export type WalletTransactionType = 'top-up' | 'gift-purchase' | 'gift-received' | 'redemption' | 'referral-bonus' | 'call-bonus' | 'payout'

export interface WalletTransaction {
  id: string
  type: WalletTransactionType
  amountNaira: number
  description: string
  status: 'completed' | 'pending'
  createdAt: string
}

export interface BankAccount {
  bankName: string
  accountNumber: string
  accountName: string
}

export interface ReferralRecord {
  id: string
  referredName: string
  bonusNaira: number
  joinedAt: string
}

export interface PayoutRequest {
  id: string
  amountNaira: number
  status: 'pending' | 'completed'
  requestedAt: string
}

export interface AdminReviewRequest {
  id: string
  targetId: string
  targetName: string
  reason: string
  createdAt: string
}

export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}
