# Flingra frontend specification

## 1. Purpose and status

This document is the implementation brief for Flingra's web frontend: routes, user journeys, page content, form fields, validation, UI states, and frontend/backend boundaries.

The repository is currently a scaffold; these pages and fields do not exist yet. Flingra is described as a Nigeria-first platform for consenting adults to discover connections and plan meetups. Where the product brief does not define an exact interaction or field, this document labels it as a **product decision** rather than treating an assumption as settled. Confirm those decisions before building the affected flow.

See the [system blueprint](../docs/architecture.md) for whole-system architecture, launch sequence, and shared security principles, and the [backend guide](../backend/README.md) for API and data conventions.

## 2. Frontend goals

- Make it clear what Flingra does and who may use it.
- Let an eligible adult create and manage a profile with minimal, understandable data collection.
- Support privacy-conscious discovery and make user safety actions easy to find.
- Provide clear feedback for every action, including permission denial, network failure, and session expiry.
- Work on mobile-sized screens, low-bandwidth connections, keyboard navigation, and assistive technology.
- Treat the API as authoritative for identity, eligibility, validation, permissions, and state changes.

## 3. Proposed stack and structure

### Stack

- React, TypeScript, and Vite.
- React Router for routing.
- Tailwind CSS and shadcn/ui for styling and accessible UI building blocks.
- TanStack Query for API/server state.
- React Hook Form and Zod for forms and client-side feedback.
- Use Zustand only for shared client-only state that does not belong in the URL, a form, or the server cache.
- Use Axios behind one typed API client if shared request configuration/interceptors are needed; do not make requests ad hoc from page components.
- Vitest for unit/component tests and Playwright for critical end-to-end flows.

These are recommendations, not installed dependencies. Keep the first implementation small and add libraries only to meet an actual need.

### Suggested source layout

```text
src/
  app/                 # App providers, route tree, layouts, error boundary
  features/
    auth/              # Sign-up, sign-in, contact verification, recovery
    onboarding/        # First-time profile setup
    discovery/         # Browse, filters, profile preview/details
    safety/            # Block, report, safety information
    profile/           # Own profile and profile editing
    settings/          # Account, privacy, security, preferences
    messaging/         # Approved connection messaging
  components/          # Reusable UI primitives and shared components
  lib/                 # Typed API client and cross-feature utilities
```

Keep feature-specific components and schemas with their feature. Promote code to shared folders only when it has a real second use.

## 4. Confirmed product direction and launch gates

The decisions below are the current product direction. They are not yet implemented. Legal/provider approval and detailed operational policies remain required before production.

- One shared app; account gender choices are male/female only. Do not add a sexual-orientation/lesbian field.
- Minimum age is 21. Sign up with email/password and verified email, or Google sign-in. Account phone-number login is not supported.
- Date of birth, government-approved proof, admin age review, and a face-based gender check are required before member features. The stated outcome of a gender-check mismatch is rejection.
- Emergency contact name and phone are required at signup. The contact is not verified or notified at signup; contact them only following a user-triggered SOS or the agreed missed-check-in escalation.
- GPS permission is required while using the app; show approximate location to compatible discovery users. A manually selected discovery area is separate from the member's reported current location.
- Profiles require 3-10 approved photos and 2-10 approved videos (up to 30 seconds each). Proposed upload caps: 10 MB per image and 100 MB per video. Server moderation must approve media before it is public.
- A male member requests a connection with a female member. She approves or declines. The requester must send the first message after approval. After three rejections from the same recipient, no further requests to that person are allowed.
- Only verified/eligible female members may start live streams.
- Calls, call credits, meetup bookings/payments, notifications, verification, and safety check-ins are in launch scope, subject to legal and provider go/no-go.
- New verified/active female profiles notify all active/eligible male accounts in-app and by push unless the female member opts out of promotion.
- Call package prices in the concept brief are draft only. VIP/VVIP and fixed host rewards are deferred.
- Meetups have a date, start time, duration, and location. Requester confirms satisfactory completion; payment release is manual. Check-ins prompt every minute during a booking; three unanswered prompts trigger an emergency-contact phone call. SOS can be triggered immediately.
- Account removal is soft deactivation/archive; profile becomes inactive/invisible. Restoration requires an application and staff decision. The request to retain user records indefinitely needs legal/privacy review before launch.

### Production gates

- Obtain legal/privacy review for age and gender checks, biometric processing, mandatory GPS, promotional notifications, archived accounts, live/call features, and meetup payments.
- Validate the face-check approach across intended users and define support/appeal handling for false rejection.
- Confirm payment provider approval, call pricing, payout/refund/dispute rules, and exact data retention.
- Define location update limits, emergency-call reliability/failure response, and staffed safety coverage.

## 5. Route and access map

Route names are proposed. Protect routes in the client for user experience, but enforce all access permissions in the backend.

| Route | Page / feature | Access | Release |
| --- | --- | --- | --- |
| `/` | Landing / welcome | Public | Core |
| `/signup` | Create account | Public | Core |
| `/login` | Sign in | Public | Core |
| `/verify-contact` | Verify email | Public, verification session | Core |
| `/verify/identity` | Submit age proof and read review status | Signed in, email verified | Core |
| `/password/forgot` | Request password reset | Public | Core |
| `/password/reset` | Set a new password from a single-use link | Public, reset token | Core |
| `/terms`, `/privacy` | Legal/policy information | Public | Core; publish approved content before launch |
| `/onboarding` | Create initial member profile | Signed in, incomplete profile | Core |
| `/discover` | Browse eligible profiles | Signed in, eligible account | Core |
| `/profiles/:profileId` | View a member profile | Signed in, eligible account | Core |
| `/settings/profile` | View/edit own profile | Signed in | Core |
| `/settings` | Account overview and sign out | Signed in | Core |
| `/settings/security` | Password/session controls | Signed in | Core |
| `/settings/privacy` | Privacy and account/data requests | Signed in | Core |
| `/settings/safety` | Emergency contact and safety settings | Signed in | Core |
| `/safety`, `/help` | Safety guidance and support | Public/member | Core |
| `/reports/new` or report dialog | Report a member/content | Signed in | Core |
| `/blocked` | View/manage blocked accounts | Signed in | Core if blocking is supported |
| `/connections` | Incoming/outgoing requests and accepted connections | Signed in | Core |
| `/inbox`, `/inbox/:conversationId` | Conversations | Signed in, accepted connection | Core |
| `/live`, `/live/:streamId` | Live-stream directory and player | Signed in; women host, eligible men join | Core |
| `/calls/:callId` | Accepted audio/video call | Signed in, connected participants | Core |
| `/bookings`, `/bookings/:bookingId` | Meetup proposals, booking, check-ins, completion | Signed in, connected participants | Core, payment gated |
| `/settings/notifications` | Notification and promotion preferences | Signed in | Core |
| `/settings/verification` | Age/gender review state | Signed in | Core |
| `/payments`, `/payments/:paymentId` | Call credits, booking payments, transaction status | Signed in | Core, provider/legal gated |
| Staff console | Moderation tools | Authorized staff only | Separate restricted app is preferred |

Unknown routes show a not-found page. A signed-out request for a protected route returns to sign-in; preserve only a safe internal destination and never put private profile, message, or report content into a redirect URL.

## 6. Shared application shell

### Public shell

- Flingra mark/name, concise service description, and clear **Join** and **Sign in** actions.
- Links to terms, privacy, safety guidance, and support.
- Do not show personal profile content or a user's session state in public metadata.

### Signed-in shell

- Primary navigation: **Discover**; add **Connections** or **Inbox** only when those features are approved and available.
- Account menu: own profile, settings, safety/help, sign out.
- Keep report/block and help actions discoverable from member profiles and any future conversation.
- On small screens, use an accessible menu with focus handling and a visible close action.

### Shared UI states

Every page or component that depends on remote data must handle:

- Initial loading and background refresh without flashing stale private data to another account.
- Empty results with a useful next action.
- Recoverable errors with retry; never convert a failed request into a success-looking empty state.
- Offline/network interruption where relevant.
- Expired session and revoked/disabled account.
- Permission denied (especially GPS), with a clear explanation if the feature is required.
- Pending moderation/review states where applicable.
- Success confirmation that does not reveal sensitive information on a shared screen or notification.

## 7. Page specifications

The fields below describe the proposed frontend contract. **Required** means required for that submitted action, not automatically mandatory profile data. Do not collect optional attributes just because a field is listed. All client validation is for usability; the backend must repeat validation and authorization.

### 7.1 Landing / welcome — `/`

**Purpose:** Explain the service, eligibility, safety approach, and next step.

**Content/actions**

- Plain-language product summary and primary **Join** / secondary **Sign in** actions.
- Brief explanation of discovery and meetups without guaranteeing safety or outcomes.
- Link to safety guidance, terms, and privacy.
- Do not display fabricated testimonials, member counts, trust badges, or verification claims.

**States:** Public page load, unavailable content fallback, and responsive navigation.

### 7.2 Sign up — `/signup`

**Purpose:** Create a credential/account and capture the minimum needed to start onboarding.

| Field | Required | Rules and UI behavior |
| --- | --- | --- |
| Email address | Required for email/password signup; verified before active use | Normalize for display; backend is authoritative. Do not expose whether an account already exists in errors. |
| Password | Required for email/password signup | Use backend policy; show/hide and password-manager compatible. Do not trim or silently alter. |
| Confirm password | Required for email/password signup | Must match; never send to API. |
| Google sign-in | Alternative signup/sign-in action | Use provider redirect/OIDC flow; do not collect Google passwords in Flingra. |
| Date of birth | Required; minimum age 21 | Accessible date entry. Backend/admin establishes eligibility; never show full DOB publicly. |
| Gender category | Required: male or female | Must match the product's verification rules. Do not add orientation fields. The check outcome is subject to server review/decision. |
| Age-proof document | Required before account activation | Upload only through the private verification flow; show accepted government document types and review status. Never place evidence in public profile or analytics. |
| Emergency contact name and phone | Required at signup; distinct from account login | Explain the number is not verified at signup and is used only for SOS or missed booking check-ins. Get confirmation that this is a trusted contact; do not send a signup notification. |
| Accept terms and privacy notice | Required, separate consent action | Link to current versions; record acceptance/version server-side. Do not pre-check. |
| Optional product updates consent | Optional, if marketing is offered | Separate, unchecked opt-in; not a condition of account creation. |

**Actions:** Submit, continue with Google, sign in instead, open legal pages. On successful registration, continue to email verification, age-proof review, or onboarding according to server-owned account state.

**Validation/states:** Required field errors adjacent to fields; generic account-exists response; password-policy hint; submission in progress; network/rate-limit response; under-21, rejected gender check, and pending admin-review states. Prevent duplicate submission while in flight.

**Security:** Never store the password in local storage, analytics, crash reports, or logs. Avoid third-party analytics on credential and recovery screens.

### 7.3 Sign in — `/login`

**Fields**

- Email or mobile number (required; label matches the accepted identifier).
- Password (required), show/hide control.
- Optional **Remember this device** only if a clear server-side session policy exists; otherwise omit.

**Actions:** Submit, forgot password, create account. If contact verification or onboarding is incomplete, route to that state after successful authentication.

**Validation/states:** Generic invalid-credentials message; disabled/loading submit; rate-limited/temporarily locked message with safe recovery route; session already active; offline/retry. Do not disclose whether the identifier exists or which part failed.

### 7.4 Contact verification — `/verify-contact`

**Fields**

- One-time code sent to the member's email, with digit/character count from the backend.
- Destination shown in masked email form.

**Actions:** Verify, resend code, change destination if policy permits, return to sign-in.

**Rules/states:** Code expiry, resend cooldown and attempt limit from server; paste and accessible per-field or single-input handling; never log the code. Show generic invalid/expired response. Prevent rapid repeated resend attempts. Do not imply verification is complete until API confirms it.

### 7.5 Password recovery — `/password/forgot` and `/password/reset`

**Request form:** Email address (required).

**Response:** Always show a neutral confirmation such as “If an account matches those details, recovery instructions will be sent.” Apply server-side rate limits.

**Reset form:** New password and confirmation; use the same password policy as signup. The reset token is short-lived and single-use; do not send it to analytics or error monitoring, and remove it from the visible URL after it is consumed if the flow allows.

**States:** Invalid/expired/used token, successful reset, network failure, and return-to-sign-in. Avoid revealing account existence.

### 7.6 Onboarding — `/onboarding`

**Purpose:** Gather the minimum profile data required for safe, useful discovery. Use short steps, a progress indicator, and a clear explanation of visibility before each sensitive or optional field. Let users save/continue later when the backend permits.

#### Step A: Basic profile

| Field | Suggested rule | Visibility |
| --- | --- | --- |
| Display name | Required; length and allowed characters configured with backend; reject whitespace-only values | Shown to other members; avoid requiring legal name unless verified need exists |
| Profile photos | At least 3 and at most 10; JPEG/PNG/WebP; max 10 MB each | Public only after moderation approval |
| Profile videos | At least 2 and at most 10; maximum 30 seconds; MP4/WebM; max 100 MB each | Public only after moderation approval |
| Bio / about me | Optional; length cap from backend; plain text | Shown to members; render as text, not HTML |

#### Step B: Gender and discovery preferences

Flingra is one shared application for all eligible adults, not separate apps by gender. The only account gender categories are male and female; no sexual-orientation field is included in the current scope.

| Field | Required | Behavior and visibility |
| --- | --- | --- |
| Gender category | Required: male or female | Used for access/connection rules. Do not expose face-check result or verification evidence. Whether to display the member's category on their public profile must be confirmed. |
| Who they want to discover | Required preference, choose male and/or female according to product rules | Private discovery preference; do not automatically publish it. |
| Who may discover them | Required preference, choose male and/or female according to product rules | Private visibility rule applied server-side; explain that it cannot prevent screenshots or exposure outside the platform. |
| Interests | Optional, if enabled | Member selects public items. |

**Discovery rule:** A profile can be returned only when it passes account/eligibility and safety rules, fits the viewer's discovery preferences, and the profile owner's visibility preferences allow that viewer. For the current connection workflow, male members request female members; female members decide whether to approve or decline.

Show a review step explaining which profile fields are public and which preferences remain private. Allow members to change discovery and visibility preferences later in settings.

#### Step C: Location

| Field | Suggested rule | Visibility |
| --- | --- | --- |
| Current GPS location | Required permission while using the platform | Update while actively using; show only approximate area/distance to compatible discovery users. Never show exact coordinates. |
| Discovery/search area | User can select a different area to browse | Affects search only; does not change or spoof reported current location. |
| Discovery distance | Bounded preference supplied by API | Used for filtering; exact current location remains private. |

**Actions:** Back, continue, save/skip optional step, finish. Explain why GPS is required; if permission is denied or unavailable, explain that member features cannot be used and provide a route to device settings. Show a review screen summarizing public profile fields and clearly distinguish private account data.

**Validation/states:** Per-step validation, upload progress/failure/retry, photo review/pending/rejected states if applicable, location permission granted/denied/unavailable, duplicate submit protection. Do not discard completed steps silently.

### 7.7 Discovery — `/discover`

**Purpose:** Browse server-selected profiles while exposing as little location and personal data as possible.

**Profile card content:** approved photos/videos, display name, approved age display, approximate area/distance, public bio/selected interests, and live status. Never render internal IDs, exact coordinates, contact details, DOB, moderation notes, or verification evidence.

**Controls**

- Filters button opens an accessible dialog/drawer.
- Filters include approved age range, distance, and selected discovery area. Gender preferences are configured in onboarding/settings and applied as server-side matching rules.
- Filter values have backend-defined bounds and defaults; provide **Reset** and **Apply**.
- GPS must be enabled to use member features. Members may choose a different search area without changing the app's current-location signal. If GPS is denied/unavailable, explain why member features are locked and how to enable it.
- Only show profiles the backend has determined are mutually compatible with the viewer's discovery preferences and the profile owner's visibility preferences. Never fetch a broad list and rely on the browser to hide incompatible profiles.
- Approximate location may update while a member is actively using the app. Do not display exact coordinates; disclose that background updates may stop when a browser is suspended or closed.

**Card actions:** Open profile, request connection (male to female only), report, and block. The server enforces the maximum three rejections from the same recipient.

**States:** Loading/skeleton; results; no matches with filter-reset suggestion; end of results/pagination; network error/retry; account ineligible; location unavailable; profile removed/unavailable. Support keyboard navigation and a non-swipe alternative if swipe gestures are ever added.

### 7.8 Member profile — `/profiles/:profileId`

**Display only API-approved public fields:** photos, display name, approved age display, coarse location, bio, and optional interests/attributes that the member chose to publish. Do not reveal private account information or exact location.

**Actions:** Back, connect (male viewer only), block, report. Confirm before block; explain that blocking affects visibility/contact according to backend behavior. Do not expose report details to the reported member.

**States:** Loading; profile unavailable/deleted/blocked; private/limited profile; action pending/success/failure; report confirmation. Ensure a profile disappearing or changing while open is handled safely.

### 7.9 Own profile and edit profile — `/settings/profile`

**Fields**

- Display name (required).
- Bio (optional, bounded plain text).
- 3-10 profile photos and 2-10 videos up to 30 seconds (add, reorder, set primary, remove).
- Any approved public attributes/interests from onboarding, with visibility labels.

**Actions:** Save, cancel/discard confirmation when there are unsaved changes, preview public profile.

**Upload behavior:** JPEG/PNG/WebP photos up to 10 MB and MP4/WebM videos up to 100 MB each; videos max 30 seconds. Backend enforces actual file type, limits, and moderation. Show progress, retry, and pending/approved/rejected states. Do not show pending or rejected media publicly. Do not include image metadata/location in public delivery.

### 7.10 Account settings — `/settings`

Show verified email in masked form, account status, links to profile/security/privacy/safety/help, emergency-contact settings, and sign out. Email changes must use a separate re-verification flow. Do not allow the frontend to edit trusted/verified status directly.

### 7.11 Security settings — `/settings/security`

**Fields/actions:** Change password (current password if required by backend, new password, confirmation); view/revoke other sessions if supported; sign out current session. Require confirmation for revoking sessions or changing credentials.

**States:** Re-authentication required, password-policy errors, success, expired session, and network error. Never display session tokens or passwords.

### 7.12 Privacy and account requests — `/settings/privacy`

**Controls:** Profile visibility choices only if supported by backend; location permission explanation; data export request if offered; account deletion request.

**Deletion confirmation:** Explain that the profile becomes inactive/invisible, sessions end, data is archived rather than erased under the current product plan, and restoration requires an application and staff decision. Require explicit confirmation and show inactive/restoration-request status. Do not promise indefinite retention until privacy/legal review is complete.

### 7.13 Report member/content — report page or accessible dialog

**Fields**

- Target is set from the profile/content being reported; show a safe summary to ensure the correct target.
- Reason/category (required; options configured by the moderation product/API).
- Description (optional; plain text with server-defined length cap).
- Evidence attachment (optional and only if a secure review/storage policy exists; omit in first release otherwise).
- Block this account as well (separate explicit choice, not silently preselected).

**Actions:** Submit report, cancel, optionally block. Show a neutral receipt and support guidance. Do not reveal whether moderation takes action or disclose report status/details to the reported user.

**States/security:** Submission progress, duplicate/previous report handling, rate limit, invalid target, retry without accidentally creating duplicate reports. Do not put report text/evidence in URLs, analytics, or ordinary logs. The backend owns authorization and staff visibility.

### 7.14 Blocked accounts — `/blocked`

List only the signed-in member's blocked accounts with the minimum identifier needed (for example display name/photo when still available). Provide unblock with confirmation and explain effects. Handle deleted/unavailable profiles. Do not imply blocking deletes historical records unless backend behavior does so.

### 7.15 Safety and help — `/safety`, `/help`

Provide reviewed, plain-language guidance for safe interactions and meetups, how to block/report, support contact, and emergency guidance appropriate to the markets served. Do not claim Flingra can guarantee a safe meetup or provide emergency response unless a staffed process exists. Keep policy content versioned and accessible without sign-in.

### 7.16 Connections and messaging

A male member can request a connection with a female member. She can approve or decline. After three rejections from the same recipient, the requester cannot send another request to that member. Show server-confirmed pending, approved, declined, or request-limit-reached states.

Approval opens a conversation, but the requester must send the first message; only after that can both members message. Include request status, inbox, message history, send/pending/failed states, and accessible safety controls. Render text safely, paginate history, and never imply delivery until confirmed by the API.

### 7.17 Live streams and calls

- Only a verified female member can start a live stream. Eligible male members can browse/join. Show live status and visible leave/report/block controls.
- Calls are available after connection approval and require the other participant to accept.
- Display server-priced call credits before purchase. Draft concept prices are NGN 2,000/10 min, NGN 4,000/15 min, NGN 7,000/30 min; retrieve current prices from the API.
- Request camera/microphone only after a user action. Show call connection state, remaining credits, end-call control, and reconnect/failure feedback. Do not record calls/live streams by default.

### 7.18 Meetup booking, payment, and safety check-ins

Booking request fields: date, start time, duration, agreed location, and the payment/terms returned by the API. The other member must review the full booking and accept it; changes after acceptance require renewed approval. Keep precise meeting location off public profiles and discovery; show it to participants only after both accept.

During the accepted booking, prompt **I'm okay** every minute. After three unanswered prompts (about three minutes), explain that an emergency-contact call is triggered. Provide a clear countdown, immediate SOS, and a false-alarm cancel action where supported. Prompts run only for the agreed booking window.

The requester confirms satisfactory completion. Display payment as pending until manual staff review/release; missing confirmation and disputes are also staff-reviewed. Show only backend-confirmed payment states and never collect card details directly.

### 7.19 Verification, notifications, and emergency contact

- **Verification:** collect DOB (21+), accepted government proof, and face-check consent; show pending admin review, approved, and rejected states. Face-check mismatch is currently configured to reject; provide a support route for appeal decisions as defined by policy. Do not imply approval guarantees safety.
- **Female-profile promotion:** in-app and push notification to active/eligible male users when a verified female profile becomes active. Female user can opt out. Respect browser/device push permission and avoid sensitive text in previews.
- **Emergency contact:** collect name and phone at signup. Explain the number is not verified and will be called only after explicit SOS or three missed one-minute check-ins during an accepted booking. Show what booking details may be shared before the booking begins.

## 8. Form, content, and validation conventions

- Put field labels outside placeholders; placeholders are examples, not accessible labels.
- Mark required/optional status in text and associate hints/errors with form controls.
- Validate on submit and, where helpful, after a field is touched. Avoid aggressive validation while users are still typing.
- Keep non-sensitive values after recoverable errors. Do not discard profile edits or report drafts silently. Clear passwords and one-time codes after successful use, expiry, or sign-out as appropriate; never persist them in browser storage.
- Use server messages for authoritative constraints, but map them to user-friendly field errors without exposing implementation details.
- Support keyboard-only use, screen readers, visible focus, sufficient contrast, zoom, and touch targets. Dialogs must trap/restore focus correctly.
- Use locale-aware date, phone, number, and currency formatting. Never infer identity, timezone, or exact location from locale alone.
- For free-text fields, enforce a documented maximum and show a count when useful. Treat all user text as untrusted.

## 9. Frontend/backend contract

Backend API paths and exact schemas are not implemented yet; agree them with backend before wiring pages. For each API operation define:

- Request/response schema, nullability, validation errors, and stable error codes.
- Authentication requirement and authorization behavior.
- Pagination/filter limits for discovery and lists.
- Loading, retry, timeout, rate-limit, and idempotency behavior for mutations.
- Whether a returned field is public, private-to-owner, or staff-only.
- Whether the result is pending review or final/confirmed.

Use typed request/response definitions and explicit view models; never render ORM-like/raw API objects wholesale. Invalidate or update TanStack Query caches after mutations, especially profile edits, blocks, and account state changes. Avoid caching precise location, reports, credentials, or other sensitive data in persistent browser storage.

## 10. Frontend security and privacy checklist

- Do not store access/refresh tokens, passwords, OTPs, reports, or precise location in `localStorage`, analytics, URLs, or console output. Prefer secure `HttpOnly` cookies with backend CSRF defenses for browser sessions.
- Do not trust hidden buttons, route guards, client-side age checks, validation, or profile visibility settings as security controls; server authorization is mandatory.
- Use safe text rendering. Avoid unsafe HTML APIs. If rich text ever becomes necessary, use a reviewed sanitizer and a narrowly defined format.
- Do not load third-party tracking on authentication, report, or other sensitive screens. Redact personal data from analytics and Sentry.
- Use a restrictive Content Security Policy and safe external-link handling as part of deployment configuration.
- Request geolocation/camera/microphone only in context after explaining why. Support deny/revoke and graceful fallback.
- Avoid exposing exact coordinates, private contact details, DOB, internal IDs, report status, moderation notes, or verification evidence in page markup, URLs, or metadata.
- Clear user-specific query/cache state on sign-out and account switch. Never show one account's cached data to another.
- Treat uploaded files, API responses, provider links, and deep links as untrusted.

## 11. Acceptance criteria for core flows

- A new eligible user can register using verified email/password or Google, submit DOB/proof and required profile/emergency-contact fields, and see admin verification state.
- An under-21, unverified, inactive, or gender-check-rejected account cannot reach protected member features, even if it manually enters a route.
- A member can inspect the public profile preview and understand which fields are visible before saving.
- Discovery returns only compatible profiles with approximate location; denied/unavailable GPS clearly blocks member features and explains recovery.
- Three profile photos and two approved videos are required before discovery; pending/rejected media stays private.
- A female member can approve/decline a male connection request; after three rejections from that recipient the requester cannot retry. Only the requester sends the first message.
- Female-only live hosting, accepted calls, credit balance, booking payment states, and location safety check-ins show server-confirmed status.
- Three missed one-minute check-ins during a booking show the emergency escalation state; immediate SOS is available.
- A member can report and block from the profile; success/failure is clear, and no private report content leaks into a URL or analytics.
- Account/session expiry returns the member to sign-in without false success or exposure of stale account data.
- Account deactivation hides the member and clearly explains archive/restoration application behavior.
- Every core screen works at mobile widths, with keyboard navigation and screen-reader labels for controls and errors.
- Client failures do not bypass backend validation, authorization, age/eligibility, or rate limits.

## 12. Testing plan

- **Vitest:** field validation, conditional steps, formatters, API error mapping, and privacy-sensitive UI behavior.
- **Component tests:** keyboard-operable forms/dialogs, focus management, loading/empty/error states, and photo/location permission states.
- **Playwright:** email/Google signup, DOB proof pending/rejected/approved, onboarding media moderation, discovery and approximate location, connection rejection limit and first-message rule, female live hosting, call credits, booking acceptance/check-ins/SOS, block/report, soft deactivation, sign-out/session expiry, and mobile navigation.
- Use synthetic accounts and content. Do not put production personal data, secrets, OTPs, or report contents in fixtures, screenshots, traces, or CI logs.

## 13. Implementation status and development commands

There is no frontend app or package manifest yet. This specification describes intended work; it does not claim that routes, fields, APIs, or tests are implemented. When bootstrapping, record the supported Node.js version and verified install, development, lint, type-check, and test commands here.
