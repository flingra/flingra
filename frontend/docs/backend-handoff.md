# Flingra frontend → backend handoff

> **Current endpoint and payload reference:** see [frontend-backend-integration-guide.md](./frontend-backend-integration-guide.md). This older document preserves functional rules and project history; where its suggested paths or response shapes differ, use the current FastAPI contract in the integration guide and `/openapi.json`.

**Historical status:** the current frontend uses backend APIs for supported product flows; `mock-db.ts` is unused legacy code. Use the [current integration guide](./frontend-backend-integration-guide.md) for wiring and provider requirements. External Paystack, LiveKit, Cloudinary, email, and SMS deployments still require environment-specific configuration and cannot be verified from this repository alone.

The sections below preserve earlier product behavior and proposed data shapes. They are historical notes, not an instruction to replace current API adapters or copy simulated behavior into the live app. Current backend support and provider requirements are summarized in [`backend/README.md`](../../backend/README.md).

The mock layer described below is historical. Do not replace current API adapters based on the old mock-to-endpoint mapping in this handoff.

See also `frontend/architecture.md` for the proposed stack (FastAPI + MySQL) and security baseline (Argon2id, HttpOnly cookies, HTTPS, input validation, rate limiting, etc.) — that document is the non-functional baseline; this document is the functional contract.

## 1. How the mock works today (so you know what to replace)

- `lib/api/client.ts` — `delay(value, ms)` just resolves after `ms` to simulate network latency. Nothing to port.
- `lib/api/mock-db.ts` — the fake database. All state lives in `sessionStorage` via a `persistedField(storageKey, initial)` helper, keyed like `flingra:session`, `flingra:own-profile`, `flingra:wallet-balance`, etc. This is **per-browser-tab fake persistence**, not a real database — every key in that file corresponds to a table or a user-scoped value you need to create for real.
- There is only ever **one real logged-in account** (`id: 'me'`) in the mock. 16 fictional seed members (`member-1`…`member-16`) act as "everyone else." Several `simulate*` functions (see §7) fake the other side of an interaction (a reply, a gift, a join request, an accept/decline) on a timer, purely because there's no second real user to drive it. **None of that simulation logic should be ported** — in the real system, the other side is a real user's own client doing the real action. Treat every `simulate*` export as a note of "this is the server-side event a real counterpart action must trigger," not as logic to copy.
- `ApiError extends Error` with a `code: string` — the frontend branches on `err.code` (e.g. `'INSUFFICIENT_BALANCE'`) to show specific UI, not just `err.message`. **Preserve every error code listed below exactly** (same string) in real API error responses, plus a human `message`. The frontend's `ApiError` class and `err instanceof ApiError` checks expect `{ code, message }` shape from whatever HTTP client wrapper replaces this mock.

## 2. Data model (`lib/api/types.ts`)

These are the canonical shapes. Field names, optionality (`?`), and unions must match exactly — components destructure these directly.

```ts
type AudiencePreference = 'men' | 'women' | 'everyone'
type AccountStage = 'needs-verification' | 'needs-onboarding' | 'active'
type SubscriptionTier = 'free' | 'vip'
type VerificationStatus = 'unverified' | 'pending' | 'verified' | 'rejected'
type VerificationDocumentType = 'NIN' | 'BVN' | 'voters-card'
type ReportReason = 'fake-profile' | 'harassment' | 'inappropriate-content' | 'underage' | 'other'
type ChatAttachmentType = 'image' | 'video' | 'file'

interface Session {
  accountId: string
  maskedContact: string       // e.g. "y•••@example.com" — never the raw email/phone
  stage: AccountStage
}

interface ProfileVideo {
  url: string
  locked?: boolean            // women-only: paywalled until viewer pays priceNaira
  priceNaira?: number
}

interface MemberProfile {
  id: string
  username: string
  displayName: string
  bio: string
  photos: string[]
  videos?: ProfileVideo[]
  ageRange: string             // e.g. "25–30" (en-dash), derived/display string
  area: string                 // human place name, e.g. "Lekki, Lagos" — NOT raw coordinates
  distanceKm: number
  interests: string[]
  discoverableBy: AudiencePreference
  wantsToDiscover: AudiencePreference
  identity: 'man' | 'woman' | 'private'
  showIdentity: boolean
  subscriptionTier: SubscriptionTier
}

interface OwnProfile extends MemberProfile {
  moderationStatus: 'approved' | 'pending' | 'rejected'
  usernameChangeAvailableAt?: string | null
  displayNameChangeAvailableAt?: string | null
  twoFactorEnabled?: boolean
  twoFactorMethod?: 'email' | 'authenticator'
  onboardingComplete?: boolean
  documentVerification?: VerificationStatus // required for all accounts (NIN/BVN/voter's card)
  documentType?: VerificationDocumentType
  vipExpiresAt?: string        // ISO date; past this, tier reverts to 'free'
}

interface DiscoveryFilters {
  minAge: number
  maxAge: number
  maxDistanceKm: number
  interests: string[]
  liveOnly: boolean
  lookingFor: AudiencePreference
}

interface PagedResult<T> { items: T[]; nextCursor: number | null }

interface BlockedAccount { id: string; displayName: string; photo: string | null; blockedAt: string }

interface Post { id: string; authorId: string; photos: string[]; video?: string; caption?: string; createdAt: string }

interface Status { id: string; authorId: string; authorName: string; authorPhoto: string; media: string; kind: 'image' | 'video'; createdAt: string }

interface LiveStream {
  id: string; hostId: string; hostName: string; hostPhoto: string; hostVideo?: string
  title: string; startedAt: string; participantIds: string[]
}

interface JoinRequest { id: string; streamId: string; requesterId: string; requesterName: string; requesterPhoto: string }

interface StreamMessage {
  id: string; streamId: string; authorId: string; authorName: string
  kind: 'message' | 'gift' | 'join'; text: string; giftId?: string; createdAt: string
}

interface GiftType { id: string; name: string; emoji: string; priceNaira: number }
interface OwnedGift { giftTypeId: string; quantity: number }
interface ReceivedGift { id: string; giftTypeId: string; fromId: string; fromName: string; valueNaira: number; redeemed: boolean; createdAt: string }

type WalletTransactionType =
  | 'top-up' | 'gift-purchase' | 'gift-received' | 'redemption' | 'referral-bonus'
  | 'call-bonus' | 'payout' | 'meetup-payment-held' | 'meetup-payment-released'
  | 'meetup-payment-refunded' | 'video-unlock' | 'vip-subscription'

interface WalletTransaction { id: string; type: WalletTransactionType; amountNaira: number; description: string; status: 'completed' | 'pending'; createdAt: string }

interface BankAccount { bankName: string; accountNumber: string; accountName: string }
interface ReferralRecord { id: string; referredName: string; bonusNaira: number; joinedAt: string }
interface PayoutRequest { id: string; amountNaira: number; status: 'pending' | 'completed'; requestedAt: string }

// Escrow-style meetup payment. See §6.5 for the full state machine.
interface MeetupPayment {
  id: string; fromId: string; fromName: string; toId: string; toName: string
  amountNaira: number
  status: 'proposed' | 'held' | 'released' | 'refunded' | 'declined'
  createdAt: string; resolvedAt?: string
}

interface AdminReviewRequest { id: string; targetId: string; targetName: string; reason: string; createdAt: string }

interface ChatThread { id: string; otherId: string; otherName: string; otherPhoto: string; lastMessage: string; lastMessageAt: string }
interface ChatAttachment { url: string; type: ChatAttachmentType; name: string }
interface DirectMessage {
  id: string; threadId: string; authorId: string; text: string
  attachment?: ChatAttachment
  paymentId?: string           // set when this message is an embedded meetup-payment proposal card
  createdAt: string
}

interface EmergencyContact { id: string; name: string; phone: string; relationship: string }
interface SafetyCheckIn { id: string; message: string; notifiedContacts: string[]; locationLink?: string; createdAt: string }
```

`VipPlan`: `{ id: string; name: string; durationDays: number; priceNaira: number }`. Current catalog (`VIP_PLANS` in `mock-db.ts`) — treat as seed data, not hardcoded:
| id | name | durationDays | priceNaira |
|---|---|---|---|
| vip-weekly | Weekly VIP | 7 | 3,500 |
| vip-monthly | Monthly VIP | 30 | 10,000 |
| vip-yearly | Yearly VIP | 365 | 80,000 |

`GiftType` catalog (`GIFT_CATALOG`):
| id | name | emoji | priceNaira |
|---|---|---|---|
| rose | Rose | 🌹 | 500 |
| fire | Fire | 🔥 | 1,000 |
| diamond | Diamond | 💎 | 5,000 |
| crown | Crown | 👑 | 10,000 |

## 3. Auth & session (`lib/api/auth.ts`)

| Function | Real endpoint (suggested) | Behavior / rules |
|---|---|---|
| `signUp({ sex, username, identifier, password, dateOfBirth, acceptedTerms, referralCode? })` → `{ stage }` | `POST /auth/signup` | Username is required, normalized to lowercase, and unique; accepted format is 3–30 letters, numbers, or underscores. Username changes are limited to once every 60 days; display-name changes are limited to once every 21 days. Reject if `!acceptedTerms` → `TERMS_REQUIRED`. **Women must sign up with a valid email** (regex `^[^\s@]+@[^\s@]+\.[^\s@]+$`) → `EMAIL_REQUIRED` if not. **Minimum age is 21 for everyone** — reject `INELIGIBLE_AGE` otherwise. Reject duplicate identifier → `ACCOUNT_EXISTS`. On success: create account in `needs-verification` stage and a draft profile with its username and `identity: sex` set. |
| `signIn({ identifier, password })` → `Session` | `POST /auth/login` | Wrong credentials → `INVALID_CREDENTIALS`. Too many attempts → `ACCOUNT_LOCKED`. Stage is `'active'` if `onboardingComplete`, else `'needs-onboarding'`. |
| `verifyContact(code)` → `{ stage }` | `POST /auth/verify-contact` | Wrong code → `INVALID_CODE`. On success, advance stage same as sign-in logic. |
| `resendCode()` | `POST /auth/resend-code` | Re-sends the OTP to email/phone. |
| `requestPasswordReset(identifier)` | `POST /auth/password/forgot` | Always succeeds client-side (don't leak account existence). |
| `resetPassword(token, password)` | `POST /auth/password/reset` | Expired/invalid token → `TOKEN_EXPIRED`. |
| `signOut()` | `POST /auth/logout` | Clears session. |
| `currentSession()` | n/a (client reads cached session) | Real client reads session from cookie/local state, not a live call every time. |
| `completeOnboarding()` | implicit side-effect of the last onboarding step | Marks the session `active` once onboarding finishes — **this must be a real, durable server-side state transition**, not just client state, or a page reload mid-flow bounces the user back into onboarding (this was an actual bug fixed in the frontend; don't reintroduce it server-side). |
| `continueWithGoogle({ username?, sex?, dateOfBirth?, acceptedTerms?, referralCode? })` → `{ stage }` | `POST /auth/oauth/google` (or redirect flow) | New Google accounts require a username and account details; existing Google sign-ins do not. Google sign-ups still go through the full onboarding flow; there is no "skip onboarding because OAuth" shortcut anywhere in the frontend. |

**Session model**: cookie-based, `HttpOnly`, server-authoritative stage (`needs-verification` → `needs-onboarding` → `active`). The frontend's route guards (`ProtectedRoute`/`PublicOnlyRoute` in `app/protected-route.tsx`) gate entire route trees on `session.stage`, so the backend must be the source of truth for which stage an account is in at all times — the frontend never infers stage from anything else. Requests to `/auth/verify-contact`, `/auth/resend-code`, `/auth/logout`, `/auth/onboarding/complete`, and authenticated profile mutations must send the `flingra_csrf` cookie value in the `X-CSRF-Token` header. In configured deployments, also send an `Origin` matching the backend's allowlist.

## 4. Profiles & discovery (`lib/api/profiles.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `getDiscoveryFeed(filters: DiscoveryFilters, cursor = 0)` → `PagedResult<MemberProfile>` | `GET /discovery?minAge&maxAge&maxDistanceKm&interests&liveOnly&lookingFor&cursor&latitude&longitude` | Implemented against verified, onboarded, approved profiles. Page size is 6. Excludes self and applies audience preferences and VIP distance waiver. Distance filtering is only applied when enabled. Synthetic profiles require the private-only `FLINGRA_DEMO_PROFILES_ENABLED` flag and are marked `isDemo`; `liveOnly` is unavailable until livestream presence is backed by the API. |
| `searchDiscoverableProfiles(query, filters)` → profile suggestions | `GET /discovery/search?q&minAge&maxAge&lookingFor` | Returns up to 10 username/display-name matches with their profile image, while applying the current discovery age/audience filters and the same verification, moderation, block, and discoverability rules. |
| `getDiscoverableProfile(id)` → `MemberProfile` | `GET /profiles/:id` | Returns only currently discoverable, email-verified, document-verified, approved profiles; otherwise 404 → `PROFILE_NOT_FOUND`. Demo profiles are hidden unless the private-only flag is enabled and are labelled as test profiles. |
| `getOwnProfile()` → `OwnProfile` | `GET /profiles/me` | No profile yet → `NO_PROFILE`. |
| `saveOwnProfile(partial: Partial<OwnProfile>)` → `OwnProfile` | `PATCH /profiles/me` | Partial update; username changes are limited to once per 60 days and display-name changes once per 21 days. The own-profile response provides each next-available timestamp. |
| `publishCurrentLocation({ latitude, longitude })` / `stopLocationSharing()` | `PUT` / `DELETE /profiles/me/location-sharing` | Sharing is explicitly enabled by the user and updates only while Discover is open. The server stops using coordinates after 5 minutes without an update. Discovery uses exact coordinates only for distance calculations and returns map coordinates rounded to 0.01 degrees. |
| `uploadPhoto(file)` → `string` (URL) | `POST /media/photos` (multipart) | Backend stores decoded/re-encoded JPEGs as authenticated Cloudinary assets and returns `{ mediaId, url, contentType, sizeBytes }`. Persist only the returned `/media/{mediaId}` URL; the database stores the Cloudinary public ID, and the backend enforces ownership and pending-review visibility before issuing a short-lived URL. The mock still returns a blob URL. |
| `uploadIdentityDocument(file, documentType)` | `POST /media/documents` (multipart `file`, `documentType`) | Required for all accounts. Stored as an authenticated Cloudinary asset; status becomes `pending`. The user media endpoint is owner-only, and authorized review admins access documents through the admin review endpoint. Messaging, livestreaming, and payments stay blocked until approved. |
| `uploadVideo(file)` → `string` (URL) | `POST /media/videos` (multipart) | Same. |
| `listVipProfiles()` → `MemberProfile[]` | `GET /profiles?subscriptionTier=vip` | Powers the `/vip` showcase page — visible to everyone, **interaction** gated separately (§6.3). |
| `listNearbyVideos()` → `{ authorId, authorName, authorPhoto, video }[]` | `GET /videos/nearby` | Only **unlocked (free)** videos — paywalled videos never appear in this teaser feed, only on the profile itself. |

`DEFAULT_FILTERS` the frontend starts with: `{ minAge: 20, maxAge: 45, maxDistanceKm: 25, interests: [], liveOnly: false, lookingFor: 'everyone' }`.

Interest tag pool (`lib/constants/interests.ts`, 28 items) and `CATEGORY_CHIPS` (10 quick filters on Discover) are UI-only constants today — if interests become backend-validated, keep the same string values so existing data doesn't mismatch.

## 5. Chat (`lib/api/chat.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `getOrCreateThread(otherId, otherName, otherPhoto)` → `ChatThread` | `POST /chat/threads` (idempotent on `otherId`) | |
| `listThreads()` → `ChatThread[]` | `GET /chat/threads` | Sorted by `lastMessageAt` desc. |
| `listMessages(threadId)` → `DirectMessage[]` | `GET /chat/threads/:id/messages` | |
| `uploadChatAttachment(file)` → `ChatAttachment` | `POST /chat/attachments` (multipart) | **25MB cap** — reject larger with `ATTACHMENT_TOO_LARGE`. Type is inferred from MIME (`image/*` → `image`, `video/*` → `video`, else `file`). |
| `sendMessage(threadId, text, attachment?)` | `POST /chat/threads/:id/messages` | Updates the thread's `lastMessage`/`lastMessageAt` (shows `📎 filename` as the preview when it's an attachment-only message). Needs to be real-time (WebSocket/SSE) for the other party — the mock fakes this with a client-side timer (`simulateReply`), which real backend should NOT port; instead push the message to the real recipient's live session. |
| `proposePaymentInChat(threadId, otherId, otherName, amountNaira)` → `DirectMessage` | `POST /chat/threads/:id/payment-proposals` | Thin wrapper: calls the same meetup-payment proposal flow as §6.5, then drops an embedded proposal card message (`paymentId` set, `text` is a human-readable summary) into the thread. |

The backend persists text threads/messages and payment-proposal cards, checks membership, verification, VIP access, and blocks, and provides private attachment upload/access. `GET /realtime/ws` authenticates with the existing HttpOnly session cookie, checks the configured `Origin`, and emits `{ id, type, data }` events. `GET /realtime/events` provides cursor-based REST polling for clients that do not use WebSockets. The current frontend chat adapter uses the backend; do not restore simulated replies as a substitute.

## 6. Business rules that span multiple features

These aren't obvious from any single file — they're invariants the frontend enforces client-side today, that must become **server-enforced** rules (never trust the client for any of these):

### 6.1 VIP distance waiver
VIP members match each other regardless of `maxDistanceKm` — this applies in both Discover (`profiles.ts: matchesFilters`) and the `/live` nearby list (`livestream.ts: listLiveStreamsNearby`, VIP hosts sort first for VIP viewers). A free viewer never gets to bypass distance, even against a VIP target. Rule: `distanceWaived = viewerIsVip && target.subscriptionTier === 'vip'`.

### 6.2 Gender/audience filtering
`lookingFor` filter on Discover maps `'men'`/`'women'` → `identity === 'man'/'woman'`; `'everyone'` disables the filter. The backend feed also intersects the viewer's identity with each candidate's `discoverableBy` and `wantsToDiscover` preferences. Livestream presence is now available from the backend for `liveOnly`; the frontend adapter still needs to send the filter.

### 6.3 VIP interaction gate (`lib/api/subscription.ts: canInteract`)
A free viewer can always **see** a VIP member's profile, but cannot message, call, or propose a meetup payment to them — the frontend replaces those action buttons with an "Upgrade to VIP" banner. **Report and Block remain available regardless of VIP status** — safety actions are never paywalled. Rule: `canInteract = target.subscriptionTier !== 'vip' || viewer.subscriptionTier === 'vip'`. Enforce this server-side on every message-send/call-start/payment-propose endpoint, not just in the UI.

### 6.4 Gender-gated features
- **Livestreaming is female-only**: `startStream` throws `LIVESTREAM_RESTRICTED` if `profile.identity !== 'woman'`. Enforce server-side.
- **Meetup payments only flow man → woman**: `proposeMeetupPayment` throws `PAYER_RESTRICTED` if the proposer isn't a man, `RECIPIENT_RESTRICTED` if the target isn't a woman. Enforce server-side.
- **Document verification (NIN/BVN/voter's card) is required for all accounts.** Pending or rejected accounts have limited access and cannot message, livestream, or make payments. Accounts are subject to manual admin review; no facial-recognition or selfie verification is used.

### 6.5 Meetup payment escrow — explicit propose/accept handshake
This is the most stateful flow in the app and was deliberately redesigned mid-project from an instant-hold model into a two-step handshake (per product decision — do not regress to instant-hold):

```
          propose (no funds move)
   payer ───────────────────────► 'proposed'
                                      │
                      recipient accepts │ recipient declines
                                      ▼                    ▼
                    'held' (funds debited from payer now)  'declined' (nothing ever charged)
                        │                    │
            either side confirms      payer requests refund
                        ▼                    ▼
                   'released'           'refunded'
            (funds credited to recipient) (funds returned to payer)
```

- `proposeMeetupPayment(toId, toName, amountNaira)` → `MeetupPayment` with `status: 'proposed'`. **No money moves at this step.** Validates payer is `man`, recipient is `woman`, `amountNaira > 0`.
- `acceptMeetupPayment(paymentId)` → debits the payer's wallet **only now**, sets `status: 'held'`. `INSUFFICIENT_BALANCE` if the payer can't cover it at acceptance time (balance is checked at accept, not at propose, since balance may have changed).
- `declineMeetupPayment(paymentId)` → `status: 'declined'`, nothing to reverse since nothing was charged.
- `confirmMeetupPayment(paymentId)` → only valid from `'held'`. Credits the recipient's wallet, sets `status: 'released'`. Either party can trigger this (meetup happened, release funds).
- `refundMeetupPayment(paymentId)` → only valid from `'held'`, **only the original payer** can call it. Returns funds to the payer, sets `status: 'refunded'`.
- The mock's `simulateRecipientResponse(paymentId)` fakes the recipient's accept/decline (85% accept) on a timer since there's no second real account — **do not port this**; in production the recipient's own client calls accept/decline for real, and that should push a notification/update to the payer's chat thread and the wallet page in real time.

Backend endpoints now implement this flow using the internal wallet ledger: `POST /chat/threads/:threadId/payment-proposals` creates the proposal without moving funds; `POST /chat/meetup-payments/:id/accept` debits the payer and holds the amount; `decline`, `release`, `refund`, and `disputes` implement the participant actions. Either party can dispute while held, and only a super admin can resolve by releasing to the recipient or refunding the payer. There is no automatic timeout/release. These holds are not regulated escrow; obtain product/legal approval before enabling real-world meetup payments.

Entry points in the UI: a "Propose a payment" button in the chat page (renders an inline Accept/Decline card via `DirectMessage.paymentId`), a matching button in the active call screen (enabled once `connected`), and a button on the profile detail page. All three call the same underlying `proposeMeetupPayment`.

### 6.6 Referrals & wallet bonuses (`lib/api/payout.ts`)
- `applyReferralCode(code)`: the mock currently credits ₦1,000 to the new signer-upper, but the backend does not issue this bonus until the reward policy is approved.
- `requestPayout(amountNaira)`: requires a saved `BankAccount` first (`NO_BANK_ACCOUNT` otherwise), `amountNaira > 0` (`INVALID_AMOUNT`), and `amountNaira <= walletStore.balanceNaira` (`INSUFFICIENT_BALANCE`). Debits the wallet immediately and creates a `'pending'` `PayoutRequest` + a `'pending'` wallet transaction — **this is where real settlement to a Nigerian bank account needs a real payout provider/rail**; the mock never actually marks a payout `'completed'`.

### 6.7 Video unlock paywall
Women's profiles can mark individual videos `locked: true, priceNaira`. `unlockVideo(url, priceNaira, authorName)` debits the viewer's wallet once per URL (`isVideoUnlocked` checks a per-viewer unlocked-URL list) and is idempotent (no-op if already unlocked). `INSUFFICIENT_BALANCE` if the viewer can't afford it.

The backend implements `POST /videos/unlock`. It reads the media owner and price from the creator's saved profile video metadata (request-supplied price/author are not trusted), caps the price at ₦3,000, and unlocks the video for 30 days. It debits the viewer and credits the creator's wallet; unlock purchases are non-refundable. The frontend should refresh the wallet and profile after unlock.

### 6.8 Call-credit billing

The backend exposes `/calls/coin-price`, `/calls/coin-packages`, `/calls/credits`, and `/calls` lifecycle routes for incoming, accept/decline, connection, heartbeat, token, status, and end operations. The server is authoritative for billing and LiveKit permissions. One credit covers one started minute: the first is charged on connection, then additional minutes are charged after each minute boundary. Packages contain 10, 15, or 30 credits; default price is ₦50 per credit and a super admin can update it. Men pay; calls without a male payer are free. The background worker settles missed billing ticks, expires unanswered or inactive calls, and retries LiveKit room cleanup. Clients must heartbeat active calls and handle `503` when provider cleanup is unavailable.

## 7. Livestreaming & gifting (`lib/api/livestream.ts`, `lib/api/wallet.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `listLiveStreams()` / `listLiveStreamsNearby()` → joined with host's `area`/`distanceKm`/`subscriptionTier`, sorted VIP-first-for-VIP-viewers then nearest | `GET /live-streams`, `GET /live-streams/nearby` | |
| `getLiveStream(id)` → `LiveStream` | `GET /live-streams/:id` | Ended/missing → `STREAM_NOT_FOUND`. |
| `startStream(title)` → `LiveStream` | `POST /live-streams` | Female-only (§6.4). No profile yet → `NO_PROFILE`. Host must send `POST /live-streams/:id/heartbeat` periodically; stale streams close after 60 seconds. |
| `endStream(id)` | `DELETE /live-streams/:id` | Also clears pending join requests for that stream. If LiveKit cleanup fails, the API reports an error and the worker retries. |
| `requestToJoin(streamId)` / `listJoinRequests(streamId)` / `respondToJoinRequest(requestId, accept)` | `POST /live-streams/:id/join-requests`, `GET /live-streams/:id/join-requests`, `PATCH /live-streams/:id/join-requests/:requestId` | Cap of **5 active speakers including the host**; the server rejects an accept beyond the cap. |
| `listParticipants(streamId)` / `listStreamViewers(streamId)` | `GET /live-streams/:id/participants`, `GET /live-streams/:id/viewers` | Backed by participant heartbeats; stale viewers expire from presence. |
| `listStreamMessages(streamId)` / `sendStreamMessage(streamId, text, kind?, giftId?)` | `GET /live-streams/:id/messages`, `POST /live-streams/:id/messages` | Persisted messages/gifts are also sent as realtime events. |
| `spendOwnedGift(giftTypeId)` → `GiftType` | `POST /wallet/gifts/:typeId/spend` | Decrements the sender's owned-gift inventory and should **credit the recipient's `ReceivedGift` list** in real backend (the mock can't do this because there's only one real account — see §1). `GIFT_NOT_FOUND` / `GIFT_NOT_OWNED` as appropriate. |
| `getOwnedGifts()` → `{ gift, quantity }[]` | `GET /wallet/gifts/owned` | |
| `buyGift(giftTypeId, quantity = 1)` → new balance | `POST /wallet/gifts/buy` | Debits wallet at catalog price × quantity. `INSUFFICIENT_BALANCE` if short. |
| `listReceivedGifts()` / `redeemGift(giftId)` / `redeemAllGifts()` | `GET /wallet/gifts/received`, `POST /wallet/gifts/:id/redeem`, `POST /wallet/gifts/redeem-all` | Redeeming credits the gift's Naira value to the recipient's wallet balance and marks it `redeemed`. |

The mock's `simulateJoinRequest`, `simulateIncomingGift`, `simulateIncomingMessage`, `simulateReceivedGift` (livestream/wallet) exist purely to make the solo-account demo feel alive — **none of this ported**; real multi-user rooms replace all of it with genuine events from other connected clients.

Backend status: wallet balance/transaction reads and gift catalog, inventory, send, receive, and redemption use the persistent ledger. Gift sending records the recipient's received gift and redemption credits the recipient once. Live-stream listing/control, LiveKit media connection, join requests, participant/viewer accounting, stream messages/gifts, and realtime event delivery are implemented. The host must call `POST /live-streams/:id/heartbeat` periodically; after 60 seconds without a host heartbeat the background worker ends the stream and closes its LiveKit room. The current frontend livestream adapter uses these backend routes.

## 8. VIP subscription (`lib/api/subscription.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `getSubscriptionStatus()` → `{ tier, expiresAt? }` | `GET /subscriptions/me` | If `vipExpiresAt` is in the past, report `tier: 'free'` even if the stored profile still says `'vip'` — **lazy expiry check, not a cron**; real backend can do either (lazy check or a scheduled downgrade job) but must give the same answer. |
| `subscribeToVip(planId)` → `{ tier: 'vip', expiresAt }` | `POST /subscriptions` | Unknown plan → `PLAN_NOT_FOUND`. No profile → `NO_PROFILE`. Insufficient balance → `INSUFFICIENT_BALANCE`. **Stacks**: if already VIP and not yet expired, the new duration extends from the *current* `vipExpiresAt`, not from now. Debits wallet at plan price, logs a `vip-subscription` transaction. |

The backend exposes the plan catalog and current subscription status and debits an already-settled internal wallet balance for purchases. Paystack wallet funding is available server-side but not yet wired to the frontend adapter.

## 9. Identity verification (new `/settings/verification` feature)

Not its own API file yet — reads/writes land on `OwnProfile` fields directly via `saveOwnProfile`. Model it as a first-class verification resource if useful, but preserve these semantics:

- **Government ID (NIN / BVN / voter's card)**: required for **all accounts**, uploaded from `/settings/verification`, stays `'pending'` after upload (not auto-approved — modeled as realistic: a human/automated review step happens after submission, out of scope of this frontend). `documentType` records which ID type was submitted. Messaging, livestreaming, and payments require an approved status.
- Google OAuth sign-ups go through the same onboarding and manual admin-review flow; there is no OAuth shortcut around review.

## 10. Wallet, payments & payouts — what's real vs. what's a placeholder

Be precise about this boundary when scoping backend work:

- **External real-money rails are wired but provider-dependent.** `fundWallet(amountNaira)` opens the Paystack-hosted checkout; `POST /wallet/top-ups` settles only after server-side verification or a signed webhook. Paystack Transfers support bank recipient setup and payout requests; transfers settle/refund only from signed webhooks. Endpoints are `GET /payout/banks`, `GET/PUT /payout/bank-account`, and `GET/POST /payouts` (the create request requires `Idempotency-Key`).
- **Internal ledger unit:** wallet and catalog amounts are stored as integer kobo in the backend. Existing API responses use whole-naira display values to preserve the frontend contract; provider adapters must convert to/from kobo explicitly and must never credit a wallet from an unverified client callback.
- Gifts, VIP, video unlocks, meetup holds, and payouts use the backend wallet ledger. Keep the existing transaction-type taxonomy when wiring the client wallet so the wallet/transactions page remains compatible.
- `getBankAccount()` / `saveBankAccount(account: BankAccount)` (`lib/api/payout.ts`) — a single bank account per user today (`BankAccount: { bankName, accountNumber, accountName }`), validated non-empty only (`INVALID_BANK_ACCOUNT`) — no real bank-account-number validation (e.g. NUBAN checksum) yet; consider adding it server-side.

Backend status: wallet balances, top-ups, transfers/payouts, meetup holds/disputes, and wallet transactions are persisted. `GET /referrals/code` returns the signed-in member's code; bonus credits are disabled until product confirms the referral policy. Paystack settings and a public webhook endpoint must be configured before real-money use. Payouts in `initiating` status after provider/network errors need reconciliation before retrying.

## 11. Safety (`lib/api/safety.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `reportMember({ targetId, reason, description?, alsoBlock })` | `POST /safety/reports` | `reason` is one of the `ReportReason` union. If `alsoBlock`, also blocks (see next). |
| `blockMember(targetId)` / `unblockMember(targetId)` / `listBlocked()` | `POST /safety/blocks`, `DELETE /safety/blocks/:id`, `GET /safety/blocks` | **Blocking is immediate and unconditional — a safety invariant, never delayed or made approval-gated.** Every block also files an `AdminReviewRequest` so repeat/serious reports can lead to a ban after human review — this is a real moderation queue the backend needs a real admin surface for (none exists in this frontend; it's out of scope here but the data model (`AdminReviewRequest`) is already defined and expected). |
| `listEmergencyContacts()` / `addEmergencyContact({ name, phone, relationship })` / `removeEmergencyContact(id)` | `GET/POST/DELETE /safety/emergency-contacts` | `INVALID_CONTACT` if name or phone empty. |
| `listSafetyCheckIns()` / `notifyEmergencyContacts(message, locationLink?)` | `GET /safety/check-ins`, `POST /safety/check-ins` | **No real SMS/call goes out from the frontend today** — this needs a real provider (e.g. Termii, as noted in `architecture.md`) wired in on the backend. `NO_CONTACTS` if the user has none saved yet. |
| `getCurrentLocationLink()` → Google-Maps link or `null` | n/a (pure browser Geolocation wrapper, client-side only) | Produces `https://maps.google.com/?q=lat,lng` from the browser's geolocation API; resolves `null` on denial/failure/no support. This one is genuinely client-only — nothing to port, but note that a raw lat/lng link is being sent to emergency contacts verbatim; confirm that's the intended precision/privacy tradeoff for a safety feature (architecture.md's privacy baseline says minimize precise location exposure — this flow is a deliberate, consented exception since the user is actively requesting help, but flag it explicitly if backend/legal wants a different approach).

Backend status: blocks and reports are persisted, blocks affect discovery immediately, and safety-reviewer admin endpoints expose/resolve the moderation queue. Emergency contacts are persisted. Check-in history is readable, but a check-in POST returns `503` until an SMS provider is configured; no contact is represented as notified when no SMS was sent. The frontend safety adapter still needs wiring to these endpoints.

## 12. Settings (`lib/api/settings.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `changePassword(currentPassword, newPassword)` | `POST /settings/password` | Wrong current password → `WRONG_PASSWORD`. |
| `listSessions()` / `revokeSession(id)` | `GET /settings/sessions`, `DELETE /settings/sessions/:id` | Device/session list (`DeviceSession: { id, device, lastActive, current }`) — real version needs actual multi-device session tracking tied to the auth/session system in §3. |
| `requestDataExport()` | `POST /settings/data-export` | Returns a queued request; poll `GET /settings/data-export/:requestId` for completion and the owner's export data. |
| `requestAccountDeletion()` | `POST /settings/account/delete` | Queues soft deletion, hides the profile, disables account access, and revokes active sessions; retained records are not removed. |

Backend status: password changes and session revocation are implemented. Export and account deletion requests are durably queued and processed by `python -m app.privacy_worker`; deletion immediately revokes active sessions and preserves records for legal and safety needs. The frontend adapter is not yet wired.

## 13. Posts & status (`lib/api/posts.ts`, `lib/api/status.ts`)

| Function | Endpoint | Notes |
|---|---|---|
| `createPost({ photos, video?, caption? })` | `POST /posts` | Requires **at least 3 photos OR 1 video** (`POST_MEDIA_REQUIRED` otherwise). |
| `listMyPosts()` / `deletePost(id)` | `GET /posts/me`, `DELETE /posts/:id` | |
| `listNearbyStatuses()` → `Status[]` | `GET /statuses/nearby` | 24-hour-style ephemeral media feed (seed data doesn't currently model expiry — add TTL/expiry server-side if that's the intended semantics). |
| `createStatus(file)` → `Status` | `POST /statuses` (multipart) | Video statuses capped at **50 seconds** (`MAX_STATUS_VIDEO_SECONDS`), checked client-side via `<video>` duration before upload — **re-validate server-side**, don't trust the client check. `STATUS_VIDEO_TOO_LONG` if over. |

Backend status: own-post CRUD and nearby image/video-status reads are implemented. A post accepts at least three owned photos or one owned video uploaded through `POST /media/videos?purpose=post`; regular `/media/videos` uploads are profile videos. Uploaded status videos are size- and file-signature-validated and expire after 24 hours. Video-duration limits are not yet validated server-side, despite the 50-second UI limit; enforce this before relying on that limit for moderation. The current frontend post/status adapters use these APIs.

## 14. Presence (`lib/api/presence.ts`)

`getPresence(authorId)` → `{ hasStatus, isLive, streamId? }`. The frontend adapter uses the backend's `GET /presence/{author_id}` for persisted status and livestream presence. Consider Redis only after measured load justifies it.

## 15. Routes (for reference — confirms which pages need which data)

From `app/router.tsx`. `ProtectedRoute allow={[...]}` gates by session stage; everything under `allow={['active']}` requires a fully onboarded session.

```
/                          landing (public)
/signup, /login            public-only (redirect away if already signed in)
/verify-contact            needs-verification
/password/forgot, /password/reset, /terms, /privacy, /safety, /help   public
/onboarding                needs-onboarding (separate OnboardingLayout, no header/bottom-nav)
/discover                  active
/profiles/:profileId       active
/messages/:threadId        active
/settings, /settings/profile, /settings/verification, /settings/security, /settings/privacy   active
/blocked                   active
/safety/emergency-contacts active
/status                    active
/live                      active (nearby livestreams list)
/live/:streamId            active (full-screen livestream takeover, no header/bottom-nav)
/vip                       active
/wallet, /gifts/shop, /gifts/redeem, /referrals, /payout   active
```

## 16. Things to sanity-check with product/legal before building the real version

These are frontend-enforced today and may need backend-side policy decisions, not just implementation:

1. **Confirmed eligibility policy:** minimum age is 21 for everyone; government ID verification is required for all accounts.
2. **Confirmed access gate:** unverified, pending, and rejected accounts may use limited features, but messaging, livestreaming, and payments require approved identity verification.
3. **Meetup payments only flow man → woman** — confirmed as the current product rule.
4. **Referral reward policy is not approved** — no referral bonuses are credited until product decides who receives a reward and the amounts.
5. **Raw lat/lng Google Maps link sent to emergency contacts** — confirm the precision tradeoff (see §11) is acceptable for the real safety feature, given `architecture.md`'s general location-minimization guidance.
6. The backend stores monetary values in kobo and exposes existing API display values in whole naira; provider integrations must convert explicitly.
