export type AudiencePreference = 'men' | 'women' | 'everyone'

export type AccountStage = 'needs-verification' | 'needs-onboarding' | 'active'

export interface Session {
  accountId: string
  maskedContact: string
  stage: AccountStage
}

export interface ProfileVideo {
  url: string
  /** Women-only: hide behind a paywall until a viewer pays `priceNaira` to unlock it. */
  locked?: boolean
  priceNaira?: number
}

export interface MemberProfile {
  id: string
  displayName: string
  bio: string
  photos: string[]
  videos?: ProfileVideo[]
  ageRange: string
  area: string
  distanceKm: number
  interests: string[]
  discoverableBy: AudiencePreference
  wantsToDiscover: AudiencePreference
  identity: 'man' | 'woman' | 'private'
  showIdentity: boolean
}

export type VerificationStatus = 'unverified' | 'pending' | 'verified' | 'rejected'
export type VerificationDocumentType = 'NIN' | 'BVN' | 'voters-card'

export interface OwnProfile extends MemberProfile {
  moderationStatus: 'approved' | 'pending' | 'rejected'
  twoFactorEnabled?: boolean
  twoFactorMethod?: 'email' | 'authenticator'
  onboardingComplete?: boolean
  /** Selfie liveness check captured during onboarding, required for every account. */
  selfieVerification?: VerificationStatus
  selfiePhoto?: string
  /** Government ID check, required for female accounts to vet claimed age/identity. */
  documentVerification?: VerificationStatus
  documentType?: VerificationDocumentType
}

export interface DiscoveryFilters {
  minAge: number
  maxAge: number
  maxDistanceKm: number
  interests: string[]
  liveOnly: boolean
  lookingFor: AudiencePreference
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

export type WalletTransactionType =
  | 'top-up'
  | 'gift-purchase'
  | 'gift-received'
  | 'redemption'
  | 'referral-bonus'
  | 'call-bonus'
  | 'payout'
  | 'meetup-payment-held'
  | 'meetup-payment-released'
  | 'meetup-payment-refunded'
  | 'video-unlock'

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

/**
 * A payment a male member sends toward meeting a female member in person. Funds
 * stay held (escrowed) until the meetup is confirmed, instead of crediting her
 * wallet immediately — this mock only ever has one logged-in account, so the
 * release/refund only ever touches that account's own balance (see wallet.ts).
 */
export interface MeetupPayment {
  id: string
  fromId: string
  fromName: string
  toId: string
  toName: string
  amountNaira: number
  status: 'held' | 'released' | 'refunded'
  createdAt: string
  resolvedAt?: string
}

export interface AdminReviewRequest {
  id: string
  targetId: string
  targetName: string
  reason: string
  createdAt: string
}

export interface ChatThread {
  id: string
  otherId: string
  otherName: string
  otherPhoto: string
  lastMessage: string
  lastMessageAt: string
}

export type ChatAttachmentType = 'image' | 'video' | 'file'

export interface ChatAttachment {
  url: string
  type: ChatAttachmentType
  name: string
}

export interface DirectMessage {
  id: string
  threadId: string
  authorId: string
  text: string
  attachment?: ChatAttachment
  createdAt: string
}

export interface EmergencyContact {
  id: string
  name: string
  phone: string
  relationship: string
}

export interface SafetyCheckIn {
  id: string
  message: string
  notifiedContacts: string[]
  locationLink?: string
  createdAt: string
}

export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}
