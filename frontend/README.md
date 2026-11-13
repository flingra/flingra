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
    messaging/         # Add only after messaging is approved
  components/          # Reusable UI primitives and shared components
  lib/                 # Typed API client and cross-feature utilities
```

Keep feature-specific components and schemas with their feature. Promote code to shared folders only when it has a real second use.

## 4. Product assumptions and decisions to confirm

The present product summary does not settle the following. Build the minimum safe default, and get a product decision before finalizing associated forms or navigation:

1. What does a user do to express interest: like, request a connection, or another action? Is mutual approval required?
2. Is messaging included in the first release, and who can message whom?
3. What identity options and discovery preferences will be supported, and which are optional/private versus shown to other members?
4. Is age eligibility established by date-of-birth declaration, a verification provider, or another age-assurance method? The frontend cannot establish age securely by itself.
5. Which location level is needed (city, area, or approximate distance), and is browser location optional?
6. Are profile photos mandatory, how many are allowed, and what moderation/review states apply?
7. Are payments, identity verification, notifications, or calls part of launch? Treat them as later modules until explicitly approved.
8. What user-visible account deletion, data export, and retention behavior is required for launch markets?

## 5. Route and access map

Route names are proposed. Protect routes in the client for user experience, but enforce all access permissions in the backend.

| Route | Page / feature | Access | Release |
| --- | --- | --- | --- |
| `/` | Landing / welcome | Public | Core |
| `/signup` | Create account | Public | Core |
| `/login` | Sign in | Public | Core |
| `/verify-contact` | Verify email or phone | Public, verification session | Core if contact verification is required |
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
| `/safety`, `/help` | Safety guidance and support | Public/member | Core |
| `/reports/new` or report dialog | Report a member/content | Signed in | Core |
| `/blocked` | View/manage blocked accounts | Signed in | Core if blocking is supported |
| `/connections` | Accepted connections/interest state | Signed in | Product decision |
| `/inbox`, `/inbox/:conversationId` | Conversations | Signed in | Later; only after messaging safety design |
| `/settings/notifications` | Notification preferences | Signed in | Later, when notifications exist |
| `/settings/verification` | Verification status/action | Signed in | Later, after verification policy/provider decision |
| `/payments`, `/payments/:paymentId` | Payment and transaction history | Signed in | Later, only if payments are approved |
| `/calls/:callId` | Live call | Signed in | Later, only if calls are approved |
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
- Permission denied (especially location), with a non-location fallback when supported.
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
| Email address or mobile number | One contact method required; decide if both are collected. Verification happens in the separate verification step if required. | Normalize on the client for display; backend is authoritative. If phone is accepted, show country calling code explicitly (Nigeria default may be suggested but must be changeable). Do not expose whether an account already exists in error text. |
| Password | Required unless a passwordless design is chosen | Use the backend's documented minimum/maximum policy; provide show/hide control and a password-manager-compatible input. Do not trim or silently alter passwords. |
| Confirm password | Required for password setup | Must match; never send this field to the API. |
| Date of birth / adult eligibility | Collect only if required by the approved age-assurance design; eligibility must be established before member features are available. | Use an accessible date entry; do not accept an underage user. Do not treat browser-only calculation or checkbox as proof of age. Do not show the date on the public profile. |
| Accept terms and privacy notice | Required, separate consent action | Link to current versions; record acceptance/version server-side. Do not pre-check. |
| Optional product updates consent | Optional, if marketing is offered | Separate, unchecked opt-in; not a condition of account creation. |

**Actions:** Submit, sign in instead, open legal pages. On successful registration, continue to contact verification or onboarding as dictated by backend state.

**Validation/states:** Required field errors adjacent to fields; generic account-exists response; password-policy hint; submission in progress; network/rate-limit response; adult eligibility failure must stop account setup without suggesting workarounds. Prevent duplicate submission while in flight.

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

- One-time code from email/SMS, with a documented digit/character count from the backend.
- Destination shown in masked form (for example, partially hidden phone/email).

**Actions:** Verify, resend code, change destination if policy permits, return to sign-in.

**Rules/states:** Code expiry, resend cooldown and attempt limit from server; paste and accessible per-field or single-input handling; never log the code. Show generic invalid/expired response. Prevent rapid repeated resend attempts. Do not imply verification is complete until API confirms it.

### 7.5 Password recovery — `/password/forgot` and `/password/reset`

**Request form:** Email/mobile identifier (required).

**Response:** Always show a neutral confirmation such as “If an account matches those details, recovery instructions will be sent.” Apply server-side rate limits.

**Reset form:** New password and confirmation; use the same password policy as signup. The reset token is short-lived and single-use; do not send it to analytics or error monitoring, and remove it from the visible URL after it is consumed if the flow allows.

**States:** Invalid/expired/used token, successful reset, network failure, and return-to-sign-in. Avoid revealing account existence.

### 7.6 Onboarding — `/onboarding`

**Purpose:** Gather the minimum profile data required for safe, useful discovery. Use short steps, a progress indicator, and a clear explanation of visibility before each sensitive or optional field. Let users save/continue later when the backend permits.

#### Step A: Basic profile

| Field | Suggested rule | Visibility |
| --- | --- | --- |
| Display name | Required; length and allowed characters configured with backend; reject whitespace-only values | Shown to other members; avoid requiring legal name unless verified need exists |
| Profile photo(s) | Product decision whether one is required; accepted formats/count/size supplied by service | Public only after upload/review policy allows |
| Bio / about me | Optional; length cap from backend; plain text | Shown to members; render as text, not HTML |

#### Step B: Identity and discovery preferences

Flingra is one shared application for all eligible adults, not separate apps by gender or sexual orientation. Onboarding should let members configure their experience without requiring them to disclose a sensitive identity publicly.

Proposed fields, pending product/privacy approval:

| Field | Required | Behavior and visibility |
| --- | --- | --- |
| Gender / identity | Optional; use inclusive, reviewed options and allow self-description or “prefer not to say” where appropriate | Private by default. Display only if the member explicitly chooses to show it. Never infer from name, photo, or behavior. |
| Who they want to discover | Member-selected one or more eligible audiences, with an inclusive “all”/custom choice if supported | Used as a private discovery preference, not automatically shown on profile. |
| Who may discover them | Member-selected audience(s), configurable separately from who they want to see | Applied by the server to discovery eligibility; explain that it controls discoverability, not guaranteed privacy from screenshots or prior interactions. |
| Connection intention / interests | Optional, only if approved for launch | Member chooses what is public; do not make sensitive answers mandatory. |

These are separate concepts: a person's identity does not determine whom they want to meet, and wanting to discover a group does not automatically make the person visible to that group. Avoid reducing matching to fixed “men's app” and “women's app” experiences.

**Discovery rule:** A profile can be returned only when it passes account/eligibility and safety rules, fits the viewer's discovery preferences, and the profile owner's visibility preferences allow that viewer. Apply this compatibility on the backend, not just as a client-side filter. For example, a man who chooses to discover women should see eligible women who have also allowed discovery by men; a woman who chooses to discover women should see eligible women who have allowed discovery by women. These examples depend on each member's selected preferences and must not be used to infer or publicly label anyone's identity.

Show a review step explaining which profile fields are public and which preferences remain private. Allow members to change their discovery and visibility preferences later in settings.

#### Step C: Location

| Field | Suggested rule | Visibility |
| --- | --- | --- |
| City/area | Prefer user-selected coarse area; required only if discovery depends on it | Show an approximate area only if user consents |
| Browser location | Optional permission prompt after explaining benefit | Never display exact coordinates to other members; support denial/manual location if product allows |
| Discovery distance | Optional preference, bounded values supplied by API | Used for filtering; exact current location remains private |

**Actions:** Back, continue, save/skip optional step, finish. Show a review screen summarizing public profile fields and clearly distinguish private account data.

**Validation/states:** Per-step validation, upload progress/failure/retry, photo review/pending/rejected states if applicable, location permission granted/denied/unavailable, duplicate submit protection. Do not discard completed steps silently.

### 7.7 Discovery — `/discover`

**Purpose:** Browse server-selected profiles while exposing as little location and personal data as possible.

**Profile card content:** approved photo, display name, age or age range only if policy permits, coarse location/distance only if consented and precision policy permits, and a short public bio/selected interests. Never render internal IDs, exact coordinates, contact details, DOB, moderation notes, or verification evidence.

**Controls**

- Filters button opens an accessible dialog/drawer.
- Proposed filter fields (confirm policy/product): age range, coarse distance, and profile attributes explicitly approved for filtering. Discovery preferences for who a member wants to see are configured in onboarding/settings and applied as matching rules, not as a substitute for identity fields.
- Filter values have backend-defined bounds and defaults; provide **Reset** and **Apply**.
- If location is not available, explain the impact and offer manual coarse-area selection if supported; browsing should not silently request permission.
- Only show profiles the backend has determined are mutually compatible with the viewer's discovery preferences and the profile owner's visibility preferences. Never fetch a broad list and rely on the browser to hide incompatible profiles.

**Card actions:** Open profile and, only after product decision, express-interest action. Avoid implying mutual interest or creating a connection before server confirmation.

**States:** Loading/skeleton; results; no matches with filter-reset suggestion; end of results/pagination; network error/retry; account ineligible; location denied; profile removed/unavailable. Support keyboard navigation and a non-swipe alternative if swipe gestures are ever added.

### 7.8 Member profile — `/profiles/:profileId`

**Display only API-approved public fields:** photos, display name, approved age display, coarse location, bio, and optional interests/attributes that the member chose to publish. Do not reveal private account information or exact location.

**Actions:** Back, optional connect/interest action (name and behavior are product decisions), block, report. Confirm before block; explain that blocking affects visibility/contact according to backend behavior. Do not expose report details to the reported member.

**States:** Loading; profile unavailable/deleted/blocked; private/limited profile; action pending/success/failure; report confirmation. Ensure a profile disappearing or changing while open is handled safely.

### 7.9 Own profile and edit profile — `/settings/profile`

**Fields**

- Display name (required).
- Bio (optional, bounded plain text).
- Profile photos (add, reorder, set primary, remove; only if photo policy is approved).
- Any approved public attributes/interests from onboarding, with visibility labels.

**Actions:** Save, cancel/discard confirmation when there are unsaved changes, preview public profile.

**Upload behavior:** Restrict client picker to allowed formats and show file-size guidance, but validate content/type/size server-side too. Show upload progress and retry. Do not include image metadata/location in public delivery; stripping metadata is a backend/media-pipeline responsibility. Explain moderation status and do not show rejected content as published.

### 7.10 Account settings — `/settings`

Show verified contact in masked form, account status, links to profile/security/privacy/help, and sign out. Contact changes must use a separate re-verification flow. Do not allow the frontend to edit trusted/verified status directly.

### 7.11 Security settings — `/settings/security`

**Fields/actions:** Change password (current password if required by backend, new password, confirmation); view/revoke other sessions if supported; sign out current session. Require confirmation for revoking sessions or changing credentials.

**States:** Re-authentication required, password-policy errors, success, expired session, and network error. Never display session tokens or passwords.

### 7.12 Privacy and account requests — `/settings/privacy`

**Controls:** Profile visibility choices only if supported by backend; location permission explanation; data export request if offered; account deletion request.

**Deletion confirmation:** Explain consequences, grace period (if any), and what happens to data before the final action. Require explicit confirmation, optionally re-authentication, and show request status. Do not promise immediate erasure unless backend policy guarantees it.

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

### 7.16 Connections and messaging — later, gated by product/safety approval

These routes are not part of the confirmed first-release scope. Before implementing them, decide consent/matching rules, who may initiate messages, blocking/reporting behavior, moderation access, retention, notification previews, and abuse response.

If approved:

- Connection list shows only server-confirmed states (pending, accepted, declined/expired as applicable); do not infer a match from a client-side action.
- Inbox lists conversation participants, safe preview text, timestamp, and unread state. Let users control sensitive previews in notifications.
- Conversation screen needs message text limits, send/pending/failed states, pagination, report/block access, and handling for a blocked/deleted participant.
- Render messages as plain text; do not execute HTML or links automatically. Uploads require a separate moderation/security design.
- WebSocket failure must fall back to a visible reconnect/polling behavior where supported; never silently drop a message.

### 7.17 Payments, verification, notifications, and calls — later modules

Only add these page families once approved in product scope and supported by backend/provider workflows:

- **Payments:** show server-confirmed amount, currency, status, and provider/reference-safe receipt. Use provider-hosted/tokenized payment UI; never collect or store card details in Flingra forms. Distinguish pending, failed, refunded, and confirmed.
- **Identity verification:** explain purpose, provider, data handling, and review/appeal states before redirect/upload. Do not collect identity evidence until retention, access, deletion, and support responsibilities are defined.
- **Notifications:** separate channel toggles from category preferences; provide safe preview controls and explain OS/browser permission is optional.
- **Calls:** request camera/microphone permission only after a user action, show clear live indicators and device errors, and provide prominent hang-up/report/block controls. Recording is off unless a separately approved consent and retention design says otherwise.

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

- A new eligible user can create an account, verify contact if required, complete required onboarding, and reach discovery; a failed step explains how to recover.
- An ineligible or unverified account cannot reach protected member features, even if it manually enters a route.
- A member can inspect the public profile preview and understand which fields are visible before saving.
- Discovery works when location is denied or unavailable, using the product-approved fallback or a clear explanation.
- A member can report and block from the profile; success/failure is clear, and no private report content leaks into a URL or analytics.
- Account/session expiry returns the member to sign-in without false success or exposure of stale account data.
- Every core screen works at mobile widths, with keyboard navigation and screen-reader labels for controls and errors.
- Client failures do not bypass backend validation, authorization, age/eligibility, or rate limits.

## 12. Testing plan

- **Vitest:** field validation, conditional steps, formatters, API error mapping, and privacy-sensitive UI behavior.
- **Component tests:** keyboard-operable forms/dialogs, focus management, loading/empty/error states, and photo/location permission states.
- **Playwright:** signup/recovery, onboarding, profile edit, discovery with location denied, profile block/report, account deletion request, sign-out/session expiry, and mobile navigation.
- Use synthetic accounts and content. Do not put production personal data, secrets, OTPs, or report contents in fixtures, screenshots, traces, or CI logs.

## 13. Implementation status and development commands

There is no frontend app or package manifest yet. This specification describes intended work; it does not claim that routes, fields, APIs, or tests are implemented. When bootstrapping, record the supported Node.js version and verified install, development, lint, type-check, and test commands here.
