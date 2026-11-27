# Flingra frontend ↔ backend integration guide

**Current-source guide:** describes the implemented FastAPI routes and frontend wiring. The generated API schema at `GET /openapi.json` and interactive docs at `/docs` are the source of truth for field constraints. Production behavior still depends on external provider credentials and dashboard configuration.

The older [backend handoff](./backend-handoff.md) describes product behavior and history. Where its suggested paths or return shapes differ from this guide, follow the current backend route and schema.

## 1. Integration rules

- Base URL is `VITE_API_URL`. `apiRequest` sends `credentials: 'include'`; the API uses HttpOnly session cookies.
- JSON request and response fields use **camelCase**. Money request/response values ending in `Naira` are whole naira integers. The backend ledger stores kobo internally.
- Mutating requests require `X-CSRF-Token`. Obtain it from the `flingra_csrf` cookie or the `X-CSRF-Token` response header; the existing helper `ensureCsrfHeaders()` bootstraps it through `GET /auth/session`. Do not set `Content-Type` on `FormData`.
- Requests from the browser must use the configured allowed origin. `Idempotency-Key` is additionally mandatory for `POST /payouts`, `POST /calls/credits/purchase`, and `POST /calls`; use a new stable key per user action and reuse it only when retrying that same action.
- For cross-origin deployments, `FLINGRA_ALLOWED_ORIGINS` must include each exact frontend origin, including its scheme and hostname (for example `https://www.flingra.com`). Add the `www` and apex domains separately if both are used; do not include a path or trailing slash.
- Success responses with HTTP `204` have no body. Errors use `{"error":{"code":"...","message":"..."}}`; request validation errors use code `INVALID_REQUEST`. Keep branching on the error `code`, not only the message.
- Identity-gated product APIs require an active, onboarded, age-eligible, document-verified account. A successful response from an earlier onboarding step does not mean later gated APIs are available.
- Upload owned media first, then send the returned `/media/{mediaId}` URL in profile, post, status, or chat requests as applicable.

## 2. Current frontend wiring status

| Frontend adapter / area | Current state |
|---|---|
| `api/auth.ts`, `api/profiles.ts`, `api/admin.ts` | Use the backend APIs. |
| `api/chat.ts`, `api/safety.ts`, `api/posts.ts`, `api/status.ts`, `api/presence.ts` | Use the backend APIs. |
| `api/livestream.ts`, `api/calls.ts` | Use backend control APIs and connect media through LiveKit when configured. |
| `api/wallet.ts`, `api/payout.ts`, `api/subscription.ts`, `api/settings.ts` | Use backend APIs. Wallet checkout and payouts depend on Paystack; referral bonus crediting is disabled. |
| Notification bell | Polls `GET /realtime/events` for durable events; the WebSocket endpoint remains available but the frontend no longer reconnects to it. |

`mock-db.ts` remains as unused legacy code; it is not the active data source for the app. Do not add simulated replies, fake recipients, incoming gifts, or referral credits to live-user flows.

## 3. Endpoint catalogue

`—` means no request body. For multipart endpoints, the form field names are listed explicitly.

### Authentication and account

| Method and path | Request | Success response |
|---|---|---|
| `POST /auth/signup` | `SignUpRequest` JSON | `201 {stage}` |
| `POST /auth/login` | `SignInRequest` JSON | `{accountId, maskedContact, stage}` |
| `POST /auth/verify-contact` | `{code}` + CSRF | `{stage}` |
| `POST /auth/resend-code` | — + CSRF | `204` |
| `GET /auth/session` | — | session object or `null` |
| `POST /auth/onboarding/complete` | — + CSRF | session object |
| `POST /auth/logout` | — + CSRF | `204` |
| `GET /auth/oauth/google/config` | — | `{clientId: string \| null}` |
| `POST /auth/oauth/google` | `{credential, nonce, username?, sex?, dateOfBirth?, acceptedTerms?, referralCode?}` | session object |
| `POST /auth/password/forgot` | `{identifier}` | `204` |
| `POST /auth/password/reset` | `{token, password}` | `204` |
| `POST /auth/2fa/email/request` | — + CSRF | `{status: "sent"}` |
| `POST /auth/2fa/email/verify` | `{code}` + CSRF | `{status: "verified"}` |
| `POST /auth/2fa/authenticator/setup` | — + CSRF | `{secret, otpauthUri, qrDataUrl}` |
| `POST /auth/2fa/authenticator/verify` | `{code}` + CSRF | `{status: "verified"}` |

Signup body:

```json
{
  "sex": "woman",
  "username": "flingra_user",
  "identifier": "person@example.com",
  "password": "example-password",
  "dateOfBirth": "1998-04-12",
  "acceptedTerms": true,
  "referralCode": "optional-code"
}
```

The backend currently sends verification codes to email. Phone identifiers are rejected with a service-unavailable response; the configured Termii integration is **not** used for signup or login OTP.

### Profile, discovery, location, and media

| Method and path | Request | Success response |
|---|---|---|
| `GET /profiles/me` | — | `OwnProfile` |
| `PATCH /profiles/me` | Partial `OwnProfilePatch` JSON + CSRF | updated `OwnProfile` |
| `GET /profiles/{profile_id}` | — | discoverable `MemberProfile` |
| `GET /profiles` | — | VIP showcase profile array |
| `GET /discovery` | Query: `minAge`, `maxAge`, `maxDistanceKm?`, repeated `interests`, `liveOnly`, `lookingFor`, `cursor`, `latitude?`, `longitude?` | `{items: MemberProfile[], nextCursor}` |
| `GET /discovery/search` | Query: `q`, `minAge`, `maxAge`, `lookingFor` | Up to 10 visible profile suggestions with `id`, `username`, `displayName`, and `photo` |
| `PUT /profiles/me/location-sharing` | `{latitude, longitude}` + CSRF | `{locationSharingEnabled: true}` |
| `DELETE /profiles/me/location-sharing` | — + CSRF | `{locationSharingEnabled: false}` |
| `GET /location/search?q=...` | Query | location suggestions |
| `GET /location/reverse?latitude=...&longitude=...` | Query | approximate display area |
| `POST /media/photos` | multipart `file` + CSRF | `{mediaId, url, contentType, sizeBytes}` |
| `POST /media/documents` | multipart `file`, `documentType` (`NIN`, `BVN`, `voters-card`) + CSRF | upload metadata |
| `POST /media/videos?purpose=profile` | multipart `file` + CSRF | upload metadata |
| `POST /media/videos?purpose=post` | multipart `file` + CSRF | upload metadata for an owned post video |
| `GET /media/{media_id}` | — | authorized media response/redirect |
| `GET /videos/nearby` | — | free/teaser video array |
| `GET /presence/{author_id}` | — | `{hasStatus, isLive, streamId?}` |

Profile patch fields include `username`, `displayName`, `bio`, `photos`, `videos`, `area`, `latitude`, `longitude`, `interests`, `discoverableBy`, `wantsToDiscover`, `identity`, `showIdentity`, `twoFactorEnabled`, and `twoFactorMethod`. Usernames are unique and accept 3–30 letters, numbers, or underscores. Username changes are limited to once every 60 days; display-name changes are limited to once every 21 days. Omit unchanged fields; do not send mock blob URLs.

### Posts and status

| Method and path | Request | Success response |
|---|---|---|
| `GET /posts/me` | — | `Post[]` |
| `POST /posts` | `{photos: string[], video?: string, caption?: string}` + CSRF | created `Post` |
| `DELETE /posts/{post_id}` | — + CSRF | `204` |
| `GET /statuses/nearby` | — | `Status[]` |
| `POST /statuses` | multipart `file` + CSRF | created `Status` |

Post body example (photo/video URLs must be backend-owned upload URLs):

```json
{
  "photos": ["/media/<media-id-1>", "/media/<media-id-2>", "/media/<media-id-3>"],
  "video": null,
  "caption": "Optional caption"
}
```

Posts require at least three owned photos or one owned post video. Status video duration is checked in the frontend UI but is **not yet validated server-side**; do not claim the 50-second limit is enforced by the API.

### Chat, meetup payments, and realtime

| Method and path | Request | Success response |
|---|---|---|
| `POST /chat/threads` | `{otherId}` + CSRF | `ChatThread` |
| `GET /chat/threads` | — | `ChatThread[]` |
| `GET /chat/threads/{thread_id}/messages` | — | `DirectMessage[]` |
| `POST /chat/threads/{thread_id}/messages` | `{text?, attachment?}` + CSRF | created `DirectMessage` |
| `POST /chat/attachments` | multipart `file` + CSRF | `{url, type, name}` |
| `POST /chat/threads/{thread_id}/payment-proposals` | `{amountNaira}` + CSRF | `MeetupPayment` |
| `GET /chat/meetup-payments` | — | payments involving the signed-in member |
| `GET /chat/meetup-payments/{payment_id}` | — | `MeetupPayment` |
| `POST /chat/meetup-payments/{payment_id}/accept` | — + CSRF | updated `MeetupPayment` |
| `POST /chat/meetup-payments/{payment_id}/decline` | — + CSRF | updated `MeetupPayment` |
| `POST /chat/meetup-payments/{payment_id}/release` | — + CSRF | updated `MeetupPayment` |
| `POST /chat/meetup-payments/{payment_id}/refund` | — + CSRF | updated `MeetupPayment` |
| `POST /chat/meetup-payments/{payment_id}/disputes` | `{reason}` + CSRF | updated `MeetupPayment` |

Message body:

```json
{
  "text": "Hi there",
  "attachment": {
    "url": "/media/<media-id>",
    "type": "image",
    "name": "photo.jpg"
  }
}
```

`text` may be empty only when an attachment is supplied. Upload chat media first; the backend accepts owned media URLs, not `blob:` URLs. `GET /chat/meetup-payments` lists payments scoped to the signed-in payer or recipient.

Poll authenticated `GET /realtime/events` for durable events. The first request returns an empty batch with a cursor; send that cursor as `?after=<last-event-id>` on later requests. Events have shape `{"id": 123, "type": "...", "data": {...}}`. Implemented event types include `chat.message`, `wallet.gift_received`, `meetup_payment.updated`, call events, and livestream events. The authenticated WebSocket `/realtime/ws` remains available to other clients; cross-origin deployments must allow the exact HTTPS origin in backend `FLINGRA_ALLOWED_ORIGINS`.

### Safety and settings

| Method and path | Request | Success response |
|---|---|---|
| `GET /safety/blocks` | — | `BlockedAccount[]` |
| `POST /safety/blocks` | `{targetId}` + CSRF | `204` |
| `DELETE /safety/blocks/{target_id}` | — + CSRF | `204` |
| `POST /safety/reports` | `{targetId, reason, description?, alsoBlock?}` + CSRF | report identifier |
| `GET /safety/emergency-contacts` | — | `EmergencyContact[]` |
| `POST /safety/emergency-contacts` | `{name, phone, relationship}` + CSRF | created contact |
| `DELETE /safety/emergency-contacts/{contact_id}` | — + CSRF | `204` |
| `GET /safety/check-ins` | — | `SafetyCheckIn[]` |
| `POST /safety/check-ins` | `{message?, locationLink?}` + CSRF | check-in, including delivery `status` |
| `POST /settings/password` | `{currentPassword, newPassword}` + CSRF | `204` |
| `GET /settings/sessions` | — | `DeviceSession[]` |
| `DELETE /settings/sessions/{session_id}` | — + CSRF | `204` |
| `POST /settings/data-export` | — + CSRF | `202 {requestId, status}` |
| `GET /settings/data-export/{request_id}` | — | `{requestId, status, result?}` |
| `POST /settings/account/delete` | — + CSRF | `202 {requestId, status}` |

Report reasons are `fake-profile`, `harassment`, `inappropriate-content`, `underage`, or `other`. Check-in `status` is `sending`, `sent`, `partially_sent`, or `failed`; use `notifiedContacts` rather than assuming every saved contact received an SMS.

### Wallet, gifts, subscriptions, referrals, and payouts

| Method and path | Request | Success response |
|---|---|---|
| `GET /wallet/balance` | — | `{balanceNaira}` |
| `GET /wallet/transactions` | — | `WalletTransaction[]` |
| `POST /wallet/top-ups` | `{amountNaira}` + CSRF | `{reference, authorizationUrl, amountNaira}` |
| `POST /wallet/top-ups/verify` | `{reference}` + CSRF | `{status: "pending", reference}` or `{status: "success", balanceNaira}` |
| `GET /wallet/gifts/catalog` | — | `GiftType[]` |
| `GET /wallet/gifts/owned` | — | `OwnedGift[]` (`giftTypeId`, `quantity`) |
| `POST /wallet/gifts/buy` | `{giftTypeId, quantity?}` + CSRF | `{balanceNaira}` |
| `POST /wallet/gifts/{gift_type_id}/spend` | `{recipientId}` + CSRF | `{giftId, name, emoji}` |
| `GET /wallet/gifts/received` | — | `ReceivedGift[]` |
| `POST /wallet/gifts/{gift_id}/redeem` | — + CSRF | `204` |
| `POST /wallet/gifts/redeem-all` | — + CSRF | `{amountNaira}` |
| `GET /subscriptions/plans` | — | `VipPlan[]` |
| `GET /subscriptions/me` | — | `{tier, expiresAt?}` |
| `POST /subscriptions` | `{planId}` + CSRF | `{tier, expiresAt?}` |
| `POST /videos/unlock` | `{url}` + CSRF | `{url, unlocked, priceNaira}` |
| `GET /videos/unlocks` | — | active unlocked media URLs |
| `GET /referrals/code` | — | referral-code object |
| `GET /referrals` | — | referral records |
| `GET /payout/banks` | — | `[{code, name}]` |
| `GET /payout/bank-account` | — | masked bank-account object or `null` |
| `PUT /payout/bank-account` | `{accountNumber, bankCode}` + CSRF | `{bankName, accountName, accountNumberMasked}` |
| `GET /payouts` | — | payout records |
| `POST /payouts` | `{amountNaira}` + CSRF and `Idempotency-Key` | `{id, reference, amountNaira, status, requestedAt}` |

The backend does **not** accept the frontend mock bank object `{bankName, accountNumber, accountName}` for writes. Load banks, send `{accountNumber, bankCode}`, and show the masked account returned by the API. Paystack-hosted checkout uses `authorizationUrl`; wallet funds are credited only after server verification or a signed webhook. Do not credit funds from the browser callback alone.

Example bank-account update:

```json
{
  "accountNumber": "0123456789",
  "bankCode": "provider-bank-code"
}
```

The backend referral code endpoint exists, but bonus crediting is disabled. `applyReferralCode()` must not keep granting mock wallet money.

### Calls and livestreams

| Method and path | Request | Success response |
|---|---|---|
| `GET /calls/coin-price` | — | `{priceNaira}` |
| `GET /calls/coin-packages` | — | `[{coins, priceNaira}]` |
| `GET /calls/credits` | — | `{coins}` |
| `POST /calls/credits/purchase` | `{coins}` + CSRF and `Idempotency-Key` | `{coins, balanceNaira}` |
| `POST /calls` | `{targetId, callType?}` + CSRF and `Idempotency-Key` | `CallSession` |
| `GET /calls/incoming` | — | incoming-call array |
| `POST /calls/{call_id}/accept` | — + CSRF | `CallSession` |
| `POST /calls/{call_id}/decline` | — + CSRF | `204` |
| `POST /calls/{call_id}/connected` | — + CSRF | `CallSession` |
| `POST /calls/{call_id}/heartbeat` | — + CSRF | `CallSession` |
| `POST /calls/{call_id}/token` | — + CSRF | `{url, token}` |
| `GET /calls/{call_id}` | — | `CallSession` |
| `DELETE /calls/{call_id}` | — + CSRF | `204` |
| `GET /live-streams` | — | `LiveStream[]` |
| `GET /live-streams/nearby` | — | streams with host area/distance/tier |
| `GET /live-streams/{stream_id}` | — | `LiveStream` |
| `POST /live-streams` | `{title?}` + CSRF | stream plus `{liveKitUrl, token}` |
| `POST /live-streams/{stream_id}/token` | — + CSRF | `{url, token}` |
| `POST /live-streams/{stream_id}/heartbeat` | — + CSRF | `204` |
| `DELETE /live-streams/{stream_id}` | — + CSRF | `204` |
| `POST /live-streams/{stream_id}/join-requests` | — + CSRF | `JoinRequest` |
| `GET /live-streams/{stream_id}/join-requests` | — | `JoinRequest[]` |
| `PATCH /live-streams/{stream_id}/join-requests/{request_id}` | `{accept: boolean}` + CSRF | updated `JoinRequest` |
| `DELETE /live-streams/{stream_id}/participants/me` | — + CSRF | `204` |
| `GET /live-streams/{stream_id}/participants` | — | member array `{id, name, photo}` |
| `GET /live-streams/{stream_id}/viewers` | — | member array `{id, name, photo}` |
| `GET /live-streams/{stream_id}/messages` | — | `StreamMessage[]` |
| `POST /live-streams/{stream_id}/messages` | `{text, kind?, giftId?}` + CSRF | created `StreamMessage` |

Call request example: `{"targetId":"<account-id>","callType":"video"}`. `callType` is `audio` or `video`; the default is `video`. Call billing and room tokens are server-authoritative. The browser should use LiveKit with the returned URL/token, send heartbeats, and respond to server state/events rather than decrementing a local balance as the source of truth.

Livestream message `kind` is `message` or `gift`; the server response may also contain `join` events. Use `recipientId` when sending a wallet gift; `giftId` in a stream message identifies the gift catalog item. The server gift-spend endpoint persists the recipient gift and emits `wallet.gift_received`.

### Admin APIs

Admin calls use the separate `flingra_admin_csrf` token and admin session cookie via `adminRequest`.

| Method and path | Request | Success response |
|---|---|---|
| `POST /admin/auth/login` | `{email, password, mfaCode?}` | `{adminId, email, role}` |
| `GET /admin/auth/session` | — | admin session or `null` |
| `POST /admin/auth/logout` | — + admin CSRF | `204` |
| `GET /admin/auth/mfa/status` | — | `{enabled}` |
| `POST /admin/auth/mfa/setup` | — + admin CSRF | `{secret, provisioningUri}` |
| `POST /admin/auth/mfa/enable`, `/mfa/disable` | `{code}` + admin CSRF | `{enabled}` |
| `POST /admin/auth/password` | `{currentPassword, newPassword}` + admin CSRF | `{status: "updated"}` |
| `GET /admin/users?search=&status=&limit=&offset=` | Query | member account summaries |
| `GET /admin/users/{account_id}` | — | member account detail |
| `POST /admin/users/{account_id}/status` | `{status: "active" \| "suspended" \| "banned", reason}` + admin CSRF | updated account status |
| `POST /admin/users/{account_id}/sessions/revoke` | — + admin CSRF | revoked session count |
| `POST /admin/users/{account_id}/wallet-adjustments` | `{amount_kobo, reason}` + admin CSRF | updated wallet balance |
| `POST /admin/users/{account_id}/call-credit-adjustments` | `{amount, reason}` + admin CSRF | updated call-credit balance |
| `PUT /admin/users/{account_id}/subscription` | `{tier, expires_at?, reason}` + admin CSRF | updated subscription |
| `GET /admin/subscriptions?tier=&limit=&offset=` | Query | member subscription queue |
| `GET /admin/subscription-plans` | — | plan catalog |
| `PATCH /admin/subscription-plans/{plan_id}` | plan fields + admin CSRF | updated plan |
| `GET /admin/reviews?type=&limit=&offset=` | Query | `{items, nextOffset}` |
| `GET /admin/reviews/{review_id}` | — | review details |
| `GET /admin/reviews/{review_id}/document` | — | protected document |
| `POST /admin/reviews/{review_id}/decision` | `{decision: "approved" \| "rejected", reason}` + admin CSRF | updated review |
| `GET /admin/safety/reviews?status=&limit=&offset=` | Query | safety review queue |
| `POST /admin/safety/reviews/{review_id}/decision` | `{decision: "reviewed" \| "dismissed", reason}` + admin CSRF | updated review |
| `GET /admin/safety/reports?status=&limit=&offset=` | Query | `{items, nextOffset}` |
| `POST /admin/safety/reports/{report_id}/decision` | `{decision: "reviewed" \| "dismissed", reason}` + admin CSRF | updated report |
| `GET /admin/users/{account_id}/audit` | optional `eventType`, `outcome`, `limit`, `offset` | `{items, nextOffset}` |
| `GET /admin/audit/events?eventType=&outcome=&accountId=&limit=&offset=` | Query | platform audit stream |
| `GET /admin/dashboard` | — | membership and engagement metrics, 30-day signup trend, and operational queue counts |
| `GET /admin/privacy/requests?status=&limit=&offset=` | Query | `{items, nextOffset}` |
| `POST /admin/privacy/requests/{request_id}/retry` | — + admin CSRF | requeued failed request |
| `GET /admin/payouts?status=&limit=&offset=` | Query | `{items, nextOffset}` |
| `GET /admin/gift-catalog` | — | gift catalog |
| `POST /admin/gift-catalog` | gift fields + admin CSRF | created gift |
| `PATCH /admin/gift-catalog/{gift_id}` | gift fields + admin CSRF | updated gift |
| `GET /admin/live-streams?status=&limit=&offset=` | Query | `{items, nextOffset}` |
| `POST /admin/live-streams/{stream_id}/end` | — + admin CSRF | closed stream |
| `GET /admin/content/posts`, `GET /admin/content/statuses` | Query | moderated content queues |
| `DELETE /admin/content/posts/{post_id}`, `DELETE /admin/content/statuses/{status_id}` | — + admin CSRF | removed content |
| `GET /admin/admins?limit=&offset=` | Query | `{items, nextOffset}` |
| `POST /admin/admins` | `{email, password, role?}` + admin CSRF | admin account |
| `PATCH /admin/admins/{target_admin_id}` | `{role?, disabled?}` + admin CSRF | updated admin account |

The admin portal includes account security settings for authenticator MFA and
password rotation. Apply database migration `000028_admin_mfa.sql` before
deploying these endpoints. MFA setup returns the authenticator secret once;
store it only in the administrator's authenticator app.
| `GET /admin/call-credits/price` | — | `{priceNaira}` |
| `PUT /admin/call-credits/price` | `{priceNaira}` + admin CSRF | `{priceNaira}` |
| `GET /admin/meetup-payments/disputes?limit=` | Query | dispute queue |
| `POST /admin/meetup-payments/{payment_id}/resolve` | `{resolution: "release" \| "refund", reason}` + admin CSRF | updated payment |

The admin console exposes member profiles and wallet history, safety
report/review, privacy request, payout, audit, staff-account, review,
meetup-dispute, and call-credit pricing surfaces. Super admins can preview and
remove private member uploads in-panel; each upload access and removal is
audited. Safety admins can monitor live streams, send room warnings, end streams,
or suspend/ban a host. Payout operations are read-only: provider retries and
manual settlement are deliberately not exposed because they can create
duplicate transfers or ledger adjustments.

### Health and provider callbacks (not browser feature APIs)

| Method and path | Use |
|---|---|
| `GET /` | Basic process liveness |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database/schema and enabled rate-limit dependency readiness |
| `POST /webhooks/paystack` | Paystack-signed payment and transfer events; provider-only, never call from frontend |

## 4. Core response shapes

```ts
type Session = {
  accountId: string
  maskedContact: string
  stage: 'needs-verification' | 'needs-onboarding' | 'active'
}

type WalletTransaction = {
  id: string
  type: string
  amountNaira: number // signed display amount
  description: string
  status: 'completed' | 'pending'
  createdAt: string
}

type MeetupPayment = {
  id: string
  fromId: string
  fromName: string
  toId: string
  toName: string
  amountNaira: number
  status: 'proposed' | 'held' | 'released' | 'refunded' | 'declined' | 'disputed'
  createdAt: string
  resolvedAt?: string | null
}

type SafetyCheckIn = {
  id: string
  message: string
  notifiedContacts: string[]
  status: 'sending' | 'sent' | 'partially_sent' | 'failed'
  locationLink: string | null
  createdAt: string
}

type MemberProfile = {
  id: string
  displayName: string
  bio: string
  photos: string[]
  videos?: Array<{ url: string; locked?: boolean | null; priceNaira?: number | null }> | null
  ageRange: string
  area: string
  latitude: number | null
  longitude: number | null
  distanceKm: number | null
  interests: string[]
  discoverableBy: 'men' | 'women' | 'everyone'
  wantsToDiscover: 'men' | 'women' | 'everyone'
  identity: 'man' | 'woman' | 'private'
  showIdentity: boolean
  subscriptionTier: 'free' | 'vip'
  isDemo?: boolean
}

type ChatThread = {
  id: string
  otherId: string
  otherName: string
  otherPhoto: string
  lastMessage: string
  lastMessageAt: string
}
type ChatAttachment = { url: string; type: 'image' | 'video' | 'file'; name: string }
type DirectMessage = {
  id: string
  threadId: string
  authorId: string
  text: string
  attachment?: ChatAttachment | null
  paymentId?: string | null
  createdAt: string
}

type Post = {
  id: string
  authorId: string
  photos: string[]
  video: string | null
  caption: string | null
  createdAt: string
}
type Status = {
  id: string
  authorId: string
  authorName: string
  authorPhoto: string
  media: string
  kind: 'image' | 'video'
  createdAt: string
}

type LiveStream = {
  id: string
  hostId: string
  hostName: string
  hostPhoto: string
  hostVideo: string | null
  title: string
  startedAt: string
  participantIds: string[]
}
type LiveJoinRequest = {
  id: string
  streamId: string
  requesterId: string
  requesterName: string
  requesterPhoto: string
  status: 'pending' | 'accepted' | 'declined' | 'expired'
  createdAt: string
}
type StreamMessage = {
  id: string
  streamId: string
  authorId: string
  authorName: string
  kind: 'message' | 'gift' | 'join'
  text: string
  giftId: string | null
  createdAt: string
}

type CallSession = {
  callId: string
  callerId: string
  calleeId: string
  callType: 'audio' | 'video'
  status: 'ringing' | 'connecting' | 'active' | 'declined' | 'ended'
  liveKitUrl: string | null
  token: string | null
  creditBalance: number | null
}

type PayoutRecord = {
  id: string
  reference: string
  amountNaira: number
  status: string
  requestedAt: string
}
```

Other response types are defined in `frontend/src/lib/api/types.ts` and the backend Pydantic response models. Keep API timestamps as ISO strings and treat nullable fields as nullable; do not substitute mock-only values.

## 5. Frontend replacement checklist

1. Replace each mock adapter listed in §2 by calling its matching endpoint through `apiRequest`/`uploadFile`; preserve UI-facing function signatures only where the API semantics match.
2. Where return shapes differ, adapt at the API boundary rather than lying to TypeScript. Examples: bank account writes use `bankCode`; owned gifts return `giftTypeId` and need catalog enrichment; payout and top-up calls return records/checkout data rather than a local numeric balance.
3. Use server-owned media URLs and refresh profile, wallet, and transaction queries after mutations.
4. Replace simulated second-user actions with server events and real actions by the other user. Do not auto-accept meetup proposals or invent incoming livestream viewers/gifts/messages.
5. Add frontend handling for endpoint error codes and pending states, especially `INSUFFICIENT_BALANCE`, `VIP_REQUIRED`, `NO_CONTACTS`, `NO_BANK_ACCOUNT`, provider `503`, and verification/access gates.
6. Smoke-test using two distinct verified test accounts for chat, gifts, meetup decisions, calls, and livestream participation. One account cannot validate recipient-side delivery or realtime behavior.
7. Keep provider secrets in backend environment only. The frontend receives only public configuration or short-lived session/room tokens.

## 6. Decisions and blockers to resolve

### Product, safety, and legal decisions

- **Launch scope and safety ownership:** the architecture blueprint treats messaging, identity verification, payments, push, and live audio/video as high-responsibility features that should launch only after abuse handling, support ownership, provider contracts, and operational readiness are agreed.
- **Meetup payment holds:** these are internal ledger holds, not regulated escrow. Decide whether to launch them at all, the dispute policy, and whether/no automatic release timeout should exist. Current behavior has no automatic release.
- **Referral rewards:** decide who receives a reward, eligibility, amount, and abuse controls. Until approved, show referral code/sharing but no bonus balance or fabricated referral records.
- **Location sharing:** approve location precision, display rounding, retention, update cadence, and emergency-contact location disclosure. The check-in UI can send a Google Maps URL containing exact coordinates.
- **Number-sharing moderation:** automatic detection/blocking of phone-number sharing was requested separately but is not part of the current route contract. Define policy, supported formats/languages, user feedback, false-positive appeals, and whether to block, mask, or queue for review before implementing.
- **Identity verification:** confirm acceptable document types, human review SLA, retention/deletion policy, and what the “verified” badge does and does not guarantee.
- **Account deletion and media retention:** agree which financial/safety records must be retained and for how long. The privacy worker queues exports/deletion, but media-provider asset cleanup and the README’s contradictory statements about privacy-request processing need verification.
- **Video statuses:** decide whether the 50-second cap is a hard product/moderation requirement; if yes, add server-side duration validation before release.
- **Phone signup:** decide whether phone signup/OTP is needed now. The current backend is email-verification based; Termii is currently wired only for safety check-in SMS.

### Termii test-key status

The user reports a **test Termii API key is present in the local backend environment**. The backend uses Termii only from `POST /safety/check-ins` to send SMS to saved emergency contacts; it does not use Termii for signup or verification OTP. Keep the key out of source control and frontend configuration. Treat check-ins as test-only until delivery has been verified with approved test recipients and sender ID, then production credentials and operational ownership are explicitly approved. Do not tell users an alert was delivered unless the API response reports that contact as successful.

### Backend/API gaps that affect frontend wiring

- Add a participant-scoped meetup-payment listing endpoint, or document the supported way to rebuild the frontend list from message payment cards.
- Add server-side status-video duration validation if the 50-second requirement is confirmed.
- Decide whether phone OTP is in launch scope before exposing the phone signup UI.
- Existing payout records in `initiating` need a safe reconciliation path; frontend retries must reuse the same idempotency key and must not trigger duplicate transfers.
- Keep the gift notification bell’s current WebSocket behavior, but connect chat/call/meetup/livestream event handlers as their screens are switched to live APIs.
