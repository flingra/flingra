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

export type SubscriptionTier = 'free' | 'vip'

export interface MemberProfile {
  id: string
  displayName: string
  bio: string
  photos: string[]
  videos?: ProfileVideo[]
  ageRange: string
  area: string
  latitude?: number | null
  longitude?: number | null
  distanceKm: number
  interests: string[]
  discoverableBy: AudiencePreference
  wantsToDiscover: AudiencePreference
  identity: 'man' | 'woman' | 'private'
  showIdentity: boolean
  subscriptionTier: SubscriptionTier
}

export interface VipPlan {
  id: string
  name: string
  durationDays: number
  priceNaira: number
}

export type VerificationStatus = 'unverified' | 'pending' | 'verified' | 'rejected'
export type VerificationDocumentType = 'NIN' | 'BVN' | 'voters-card'

export interface OwnProfile extends MemberProfile {
  moderationStatus: 'approved' | 'pending' | 'rejected'
  twoFactorEnabled?: boolean
  twoFactorMethod?: 'email' | 'authenticator'
  onboardingComplete?: boolean
  /** Government ID check, required for female accounts to vet claimed age/identity. */
  documentVerification?: VerificationStatus
  documentType?: VerificationDocumentType
  /** Set only while `subscriptionTier` is 'vip'; past this date the account reverts to free. */
  vipExpiresAt?: string
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

/** A purchasable bundle of call-credit coins. `priceNaira` is always `coins * coinPriceNaira`, computed live off the admin-set price — never stored stale. */
export interface CoinPackage {
  coins: number
  priceNaira: number
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
  | 'vip-subscription'
  | 'coin-purchase'
  | 'call-credit-spend'

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
 * A payment a male member proposes toward meeting a female member in person.
 * Nothing moves until she agrees: 'proposed' → (she accepts) 'held' → 'released',
 * or (she declines) 'declined' with no funds ever touched. While held, either side
 * can release it once the meetup happened, or the payer can ask for a refund.
 * This mock only ever has one logged-in account, so which side's wallet actually
 * moves depends on whether `fromId` or `toId` is the signed-in user (see wallet.ts).
 */
export interface MeetupPayment {
  id: string
  fromId: string
  fromName: string
  toId: string
  toName: string
  amountNaira: number
  status: 'proposed' | 'held' | 'released' | 'refunded' | 'declined'
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
  /** Set when this message is an embedded meetup-payment proposal card rather than plain text. */
  paymentId?: string
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
