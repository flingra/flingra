import { hashSeed } from '@/lib/utils'
import type {
  AdminReviewRequest,
  BankAccount,
  BlockedAccount,
  ChatThread,
  DirectMessage,
  EmergencyContact,
  GiftType,
  JoinRequest,
  LiveStream,
  MeetupPayment,
  MemberProfile,
  OwnedGift,
  OwnProfile,
  PayoutRequest,
  Post,
  ProfileVideo,
  ReceivedGift,
  ReferralRecord,
  ReportReason,
  SafetyCheckIn,
  Session,
  Status,
  StreamMessage,
  VipPlan,
  WalletTransaction,
} from './types'

/**
 * Public-domain Blender Foundation shorts (not real people), used as stand-in
 * clips on a couple of mock profiles so the video UI has something to play.
 * Flingra never fabricates video of a real-looking stranger and attaches it to a
 * fictional profile — that's a meaningfully different kind of fake than a
 * placeholder portrait photo.
 */
const SAMPLE_VIDEO = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4'
const SAMPLE_VIDEO_2 = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4'

/**
 * Backs a store field with sessionStorage so an in-memory mock session survives a
 * page refresh or direct URL navigation, the same way a real cookie-backed session
 * would. Call sites keep using plain property assignment (`store.field = value`).
 */
function persistedField<T>(storageKey: string, initial: T) {
  let value: T = initial
  try {
    const raw = sessionStorage.getItem(storageKey)
    if (raw) value = JSON.parse(raw) as T
  } catch {
    // Ignore unavailable/corrupt storage and fall back to `initial`.
  }
  return {
    get: () => value,
    set: (next: T) => {
      value = next
      try {
        if (next == null) sessionStorage.removeItem(storageKey)
        else sessionStorage.setItem(storageKey, JSON.stringify(next))
      } catch {
        // Ignore unavailable storage (e.g. private browsing quota).
      }
    },
  }
}

/** Real-face placeholder photo (pravatar's fixed pool of 70), stable per seed. */
function avatar(seed: string) {
  return `https://i.pravatar.cc/400?img=${hashSeed(seed, 70) + 1}`
}

/** A small gallery of placeholder photos for a richer profile view, stable per seed. */
function avatarGallery(seed: string, count = 3) {
  return Array.from({ length: count }, (_, i) => avatar(`${seed}-${i}`))
}

const AREAS = ['Lekki, Lagos', 'Yaba, Lagos', 'Wuse, Abuja', 'GRA, Port Harcourt', 'Bodija, Ibadan', 'Asokoro, Abuja']
const INTEREST_POOL = [
  'Afrobeats',
  'Photography',
  'Football',
  'Cooking',
  'Tech',
  'Fashion',
  'Hiking',
  'Movies',
  'Books',
  'Travel',
  'Fitness',
  'Art',
]

function pick<T>(arr: T[], n: number, offset: number): T[] {
  return Array.from({ length: n }, (_, i) => arr[(offset + i * 3) % arr.length])
}

const NAMES: { name: string; identity: MemberProfile['identity'] }[] = [
  { name: 'Amaka', identity: 'woman' },
  { name: 'Tunde', identity: 'man' },
  { name: 'Ifeoma', identity: 'woman' },
  { name: 'Chidi', identity: 'man' },
  { name: 'Zainab', identity: 'woman' },
  { name: 'Emeka', identity: 'man' },
  { name: 'Folake', identity: 'woman' },
  { name: 'Bayo', identity: 'man' },
  { name: 'Ngozi', identity: 'woman' },
  { name: 'Segun', identity: 'man' },
  { name: 'Hauwa', identity: 'woman' },
  { name: 'Obi', identity: 'man' },
  { name: 'Adaeze', identity: 'woman' },
  { name: 'Kunle', identity: 'man' },
  { name: 'Rita', identity: 'woman' },
  { name: 'Dayo', identity: 'man' },
]

function seedVideos(person: { name: string; identity: MemberProfile['identity'] }, index: number): ProfileVideo[] | undefined {
  const isWoman = person.identity === 'woman'
  if (index % 4 === 0) {
    return [
      { url: SAMPLE_VIDEO, locked: isWoman, priceNaira: isWoman ? 1500 : undefined },
      { url: SAMPLE_VIDEO_2 },
    ]
  }
  if (index % 4 === 2) {
    return [{ url: SAMPLE_VIDEO }]
  }
  return undefined
}

export const PROFILES: OwnProfile[] = NAMES.map((person, index) => ({
  id: `member-${index + 1}`,
  displayName: person.name,
  bio: 'Exploring the city, always up for good conversation and good food.',
  photos: avatarGallery(`${person.name}-${index}`),
  videos: seedVideos(person, index),
  ageRange: `${24 + (index % 10)}–${27 + (index % 10)}`,
  area: AREAS[index % AREAS.length],
  distanceKm: 2 + (index % 18),
  interests: pick(INTEREST_POOL, 3, index),
  discoverableBy: 'everyone',
  wantsToDiscover: person.identity === 'woman' ? 'men' : 'women',
  identity: person.identity,
  showIdentity: index % 3 !== 0,
  moderationStatus: 'approved',
  documentVerification: person.identity === 'woman' ? 'verified' : undefined,
  subscriptionTier: index % 5 === 1 ? ('vip' as const) : ('free' as const),
}))

/** One mock member is pre-seeded as live so the viewer flow has something to watch. */
const LIVE_HOST = PROFILES[2]
export const SEED_LIVE_STREAMS: LiveStream[] = [
  {
    id: 'stream-1',
    hostId: LIVE_HOST.id,
    hostName: LIVE_HOST.displayName,
    hostPhoto: LIVE_HOST.photos[0],
    hostVideo: LIVE_HOST.videos?.[0]?.url,
    title: `Hanging out with ${LIVE_HOST.displayName}`,
    startedAt: new Date(Date.now() - 12 * 60_000).toISOString(),
    participantIds: [LIVE_HOST.id],
  },
]

export const STATUSES: Status[] = PROFILES.filter((_, index) => index % 3 === 0).map((profile, i) => ({
  id: `status-${i + 1}`,
  authorId: profile.id,
  authorName: profile.displayName,
  authorPhoto: profile.photos[0],
  media: profile.photos[1] ?? profile.photos[0],
  kind: 'image',
  createdAt: new Date(Date.now() - i * 3600_000).toISOString(),
}))

export const GIFT_CATALOG: GiftType[] = [
  { id: 'rose', name: 'Rose', emoji: '🌹', priceNaira: 500 },
  { id: 'fire', name: 'Fire', emoji: '🔥', priceNaira: 1000 },
  { id: 'diamond', name: 'Diamond', emoji: '💎', priceNaira: 5000 },
  { id: 'crown', name: 'Crown', emoji: '👑', priceNaira: 10000 },
]

export const VIP_PLANS: VipPlan[] = [
  { id: 'vip-weekly', name: 'Weekly VIP', durationDays: 7, priceNaira: 3500 },
  { id: 'vip-monthly', name: 'Monthly VIP', durationDays: 30, priceNaira: 10000 },
  { id: 'vip-yearly', name: 'Yearly VIP', durationDays: 365, priceNaira: 80000 },
]

/** Coin bundle sizes the store offers. Each bundle's price is `coins * coinPriceStore.priceNaira`, computed live. */
export const COIN_PACKAGE_SIZES = [10, 15, 30]

/** Default price before an admin ever sets one, in ₦ per call-credit coin. */
export const DEFAULT_COIN_PRICE_NAIRA = 50

export const CURRENT_ACCOUNT = {
  id: 'me',
  identifier: 'you@example.com',
  maskedContact: 'y•••@example.com',
  password: 'Password1!',
  verificationCode: '123456',
}

const sessionField = persistedField<Session | null>('flingra:session', null)
export const sessionStore = {
  get session() {
    return sessionField.get()
  },
  set session(value: Session | null) {
    sessionField.set(value)
  },
}

const ownProfileField = persistedField<OwnProfile | null>('flingra:own-profile', null)
export const ownProfileStore = {
  get profile() {
    return ownProfileField.get()
  },
  set profile(value: OwnProfile | null) {
    ownProfileField.set(value)
  },
}

const blockedField = persistedField<BlockedAccount[]>('flingra:blocked', [])
export const blockedStore = {
  get blocked() {
    return blockedField.get()
  },
  set blocked(value: BlockedAccount[]) {
    blockedField.set(value)
  },
}

const reportsField = persistedField<{ id: string; targetId: string; reason: ReportReason }[]>('flingra:reports', [])
export const reportStore = {
  get reports() {
    return reportsField.get()
  },
  set reports(value: { id: string; targetId: string; reason: ReportReason }[]) {
    reportsField.set(value)
  },
}

const postsField = persistedField<Post[]>('flingra:posts', [])
export const postStore = {
  get posts() {
    return postsField.get()
  },
  set posts(value: Post[]) {
    postsField.set(value)
  },
}

const statusesField = persistedField<Status[]>('flingra:statuses', [])
export const statusStore = {
  get statuses() {
    return statusesField.get()
  },
  set statuses(value: Status[]) {
    statusesField.set(value)
  },
}

const liveStreamsField = persistedField<LiveStream[]>('flingra:live-streams', SEED_LIVE_STREAMS)
export const liveStreamStore = {
  get streams() {
    return liveStreamsField.get()
  },
  set streams(value: LiveStream[]) {
    liveStreamsField.set(value)
  },
}

const joinRequestsField = persistedField<JoinRequest[]>('flingra:join-requests', [])
export const joinRequestStore = {
  get requests() {
    return joinRequestsField.get()
  },
  set requests(value: JoinRequest[]) {
    joinRequestsField.set(value)
  },
}

const streamMessagesField = persistedField<StreamMessage[]>('flingra:stream-messages', [
  {
    id: 'msg-seed-1',
    streamId: 'stream-1',
    authorId: SEED_LIVE_STREAMS[0].hostId,
    authorName: SEED_LIVE_STREAMS[0].hostName,
    kind: 'message',
    text: 'Welcome everyone! 👋',
    createdAt: new Date(Date.now() - 11 * 60_000).toISOString(),
  },
])
export const streamMessageStore = {
  get messages() {
    return streamMessagesField.get()
  },
  set messages(value: StreamMessage[]) {
    streamMessagesField.set(value)
  },
}

const walletBalanceField = persistedField<number>('flingra:wallet-balance', 5000)
export const walletStore = {
  get balanceNaira() {
    return walletBalanceField.get()
  },
  set balanceNaira(value: number) {
    walletBalanceField.set(value)
  },
}

const transactionsField = persistedField<WalletTransaction[]>('flingra:wallet-transactions', [
  {
    id: 'txn-seed-1',
    type: 'wallet-top-up',
    amountNaira: 5000,
    description: 'Welcome credit',
    status: 'completed',
    createdAt: new Date(Date.now() - 2 * 86_400_000).toISOString(),
  },
])
export const transactionStore = {
  get transactions() {
    return transactionsField.get()
  },
  set transactions(value: WalletTransaction[]) {
    transactionsField.set(value)
  },
}

const ownedGiftsField = persistedField<OwnedGift[]>('flingra:owned-gifts', [])
export const ownedGiftStore = {
  get owned() {
    return ownedGiftsField.get()
  },
  set owned(value: OwnedGift[]) {
    ownedGiftsField.set(value)
  },
}

const receivedGiftsField = persistedField<ReceivedGift[]>('flingra:received-gifts', [
  {
    id: 'gift-seed-1',
    giftTypeId: 'rose',
    fromId: 'member-2',
    fromName: 'Tunde',
    valueNaira: 500,
    redeemed: false,
    createdAt: new Date(Date.now() - 3 * 3600_000).toISOString(),
  },
  {
    id: 'gift-seed-2',
    giftTypeId: 'diamond',
    fromId: 'member-4',
    fromName: 'Chidi',
    valueNaira: 5000,
    redeemed: false,
    createdAt: new Date(Date.now() - 26 * 3600_000).toISOString(),
  },
])
export const receivedGiftStore = {
  get gifts() {
    return receivedGiftsField.get()
  },
  set gifts(value: ReceivedGift[]) {
    receivedGiftsField.set(value)
  },
}

const bankAccountField = persistedField<BankAccount | null>('flingra:bank-account', null)
export const bankAccountStore = {
  get account() {
    return bankAccountField.get()
  },
  set account(value: BankAccount | null) {
    bankAccountField.set(value)
  },
}

const referralsField = persistedField<ReferralRecord[]>('flingra:referrals', [
  { id: 'ref-seed-1', referredName: 'Bisi O.', bonusNaira: 1000, joinedAt: new Date(Date.now() - 5 * 86_400_000).toISOString() },
])
export const referralStore = {
  get referrals() {
    return referralsField.get()
  },
  set referrals(value: ReferralRecord[]) {
    referralsField.set(value)
  },
}

const payoutRequestsField = persistedField<PayoutRequest[]>('flingra:payout-requests', [])
export const payoutRequestStore = {
  get requests() {
    return payoutRequestsField.get()
  },
  set requests(value: PayoutRequest[]) {
    payoutRequestsField.set(value)
  },
}

const adminReviewField = persistedField<AdminReviewRequest[]>('flingra:admin-reviews', [])
export const adminReviewStore = {
  get requests() {
    return adminReviewField.get()
  },
  set requests(value: AdminReviewRequest[]) {
    adminReviewField.set(value)
  },
}

const emergencyContactsField = persistedField<EmergencyContact[]>('flingra:emergency-contacts', [])
export const emergencyContactStore = {
  get contacts() {
    return emergencyContactsField.get()
  },
  set contacts(value: EmergencyContact[]) {
    emergencyContactsField.set(value)
  },
}

const safetyCheckInsField = persistedField<SafetyCheckIn[]>('flingra:safety-check-ins', [])
export const safetyCheckInStore = {
  get checkIns() {
    return safetyCheckInsField.get()
  },
  set checkIns(value: SafetyCheckIn[]) {
    safetyCheckInsField.set(value)
  },
}

const chatThreadsField = persistedField<ChatThread[]>('flingra:chat-threads', [])
export const chatThreadStore = {
  get threads() {
    return chatThreadsField.get()
  },
  set threads(value: ChatThread[]) {
    chatThreadsField.set(value)
  },
}

const directMessagesField = persistedField<DirectMessage[]>('flingra:direct-messages', [])
export const directMessageStore = {
  get messages() {
    return directMessagesField.get()
  },
  set messages(value: DirectMessage[]) {
    directMessagesField.set(value)
  },
}

const meetupPaymentsField = persistedField<MeetupPayment[]>('flingra:meetup-payments', [
  {
    id: 'meetup-seed-1',
    fromId: 'member-2',
    fromName: 'Tunde',
    toId: 'me',
    toName: 'You',
    amountNaira: 5000,
    status: 'held',
    createdAt: new Date(Date.now() - 4 * 3600_000).toISOString(),
  },
  {
    id: 'meetup-seed-2',
    fromId: 'member-9',
    fromName: 'Segun',
    toId: 'me',
    toName: 'You',
    amountNaira: 8000,
    status: 'proposed',
    createdAt: new Date(Date.now() - 20 * 60_000).toISOString(),
  },
])
export const meetupPaymentStore = {
  get payments() {
    return meetupPaymentsField.get()
  },
  set payments(value: MeetupPayment[]) {
    meetupPaymentsField.set(value)
  },
}

/** Video URLs the signed-in viewer has paid to unlock on other members' profiles. */
const unlockedVideosField = persistedField<string[]>('flingra:unlocked-videos', [])
export const unlockedVideoStore = {
  get urls() {
    return unlockedVideosField.get()
  },
  set urls(value: string[]) {
    unlockedVideosField.set(value)
  },
}

/** Admin-set ₦ price per call-credit coin. One global price, not per-user. */
const coinPriceField = persistedField<number>('flingra:coin-price-naira', DEFAULT_COIN_PRICE_NAIRA)
export const coinPriceStore = {
  get priceNaira() {
    return coinPriceField.get()
  },
  set priceNaira(value: number) {
    coinPriceField.set(value)
  },
}

/** The signed-in account's call-credit coin balance, spent while on a call. */
const callCreditsField = persistedField<number>('flingra:call-credits', 0)
export const callCreditStore = {
  get coins() {
    return callCreditsField.get()
  },
  set coins(value: number) {
    callCreditsField.set(value)
  },
}
