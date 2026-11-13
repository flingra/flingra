# Flingra backend implementation and API contract

## 1. Purpose and status

This is the backend developer's implementation guide and the frontend team's proposed integration contract. It describes the Go service, core domain boundaries, HTTP behavior, endpoint inventory, example payloads, and security/operational requirements.

The repository is currently a scaffold: no API, Go module, database schema, OpenAPI file, or provider integration exists yet. The endpoints and JSON below are proposed contracts to implement and then capture in the OpenAPI specification. Confirm the guarded assumptions in §16 before freezing affected schemas. Once implementation begins, the OpenAPI document and tests—not prose examples—must be the source of truth.

Flingra is one application for all eligible adults. Discovery preferences and profile visibility are separate, user-controlled concepts; they are not inferred from identity. See the [system blueprint](../docs/architecture.md) and [frontend specification](../frontend/README.md).

## 2. Backend goals and first-release scope

Build a secure, reliable modular monolith that supports the approved first-release scope:

- Email/password with verified email and Google sign-in; required emergency-contact number.
- 21+ eligibility, government-document review by an administrator, and male/female account categories.
- Member profiles with at least 3 and at most 10 approved photos, and 2 to 10 approved videos (30 seconds maximum each).
- Required GPS permission while using the platform, approximate location for compatible discovery, and a separate manually selected discovery area.
- Male-to-female connection requests; female recipient approval/decline; requester must send the first chat message after approval. Three rejections by the same recipient permanently exhaust that requester's attempts to connect to that recipient.
- Women-only live streaming, in-app notifications and push, audio/video calls, call credits, and meetup payments, subject to legal and payment-provider go/no-go approval.
- Blocking, reporting, admin review/moderation, and soft deactivation with a staff-reviewed restoration application.
- Operational health, structured redacted logs, and observable failures.

VIP/VVIP memberships and host rewards are not defined for this release. Do not build those financial flows until terms, pricing, unit economics, legal permissibility, provider approval, and dispute handling are separately decided.

## 3. Proposed stack

- **Language:** Go; pin the supported Go toolchain in `go.mod`, CI, and the container image once the application is bootstrapped.
- **HTTP:** Standard library `net/http` and `ServeMux` initially. Adopt a focused router only if routing complexity warrants it.
- **Contract:** OpenAPI 3.x, checked into `backend/api/openapi.yaml`. Use it for review, frontend types/client generation if adopted, and API contract tests.
- **Database:** MySQL 8.4 LTS through `database/sql` and a maintained MySQL driver. Keep SQL parameterized; consider `sqlc` after the team agrees on the query workflow.
- **Migrations:** Ordered SQL migration files run as an explicit deployment step using a selected migration tool. Do not auto-run schema changes on every API startup.
- **Testing:** Go `testing`, `httptest`, and integration tests against disposable MySQL.
- **Operations:** Docker, GitHub Actions, health/readiness endpoints, structured logs, and Sentry or an equivalent error-monitoring provider.

Keep the service single-deployable, but use durable asynchronous processing for media moderation, notification delivery, provider webhooks, and scheduled booking check-ins. A general Redis cache is optional; do not make a safety timer depend only on an in-memory timer that disappears on process restart.

## 4. Suggested Go layout

```text
backend/
  cmd/api/                  # process entry point and dependency wiring
  internal/
    auth/                   # credentials, sessions, Google OIDC, verification
    member/                 # member lifecycle and eligibility state
    profile/                # profile editing and public profile view
    discovery/              # preferences and eligible candidate selection
    connections/            # request/approve/decline and requester limits
    messaging/              # approved-connection conversation rules
    media/                  # private upload, review, approved derivatives
    realtime/               # live/call provider adapters and metering
    payments/               # call-credit ledger and meetup payment state
    notifications/          # in-app/push delivery and preferences
    safety/                 # blocks, reports, staff moderation boundary
    location/               # permissioned input, coarse indexing/visibility
    jobs/                   # durable moderation, notification, and check-in work
    platform/
      config/               # validated configuration
      database/             # connection setup and transaction helpers
      http/                 # middleware, response/error encoding
      observability/        # redacted logs, metrics, tracing
  migrations/               # versioned SQL migrations
  api/openapi.yaml          # reviewed HTTP contract
  go.mod
```

Keep domain rules out of HTTP handlers. Feature packages should own their rules and persistence queries; avoid a generic repository abstraction for every table. Use interfaces where they make a real boundary testable, such as a provider client or clock.

## 5. HTTP conventions

- Prefix application routes with `/api/v1`. Serve OpenAPI docs in development; restrict or disable interactive docs in production if they reveal internal details.
- Use JSON (`application/json; charset=utf-8`) for API bodies, UTF-8 text, and UTC RFC 3339 timestamps.
- Set explicit request-body limits and timeouts. Reject malformed JSON, unknown fields where safe, invalid enum values, oversized strings, and unsupported content types.
- Use explicit transport/request/response structs. Never serialize database structs or internal domain objects directly.
- Use server-assigned IDs; do not treat an unguessable ID as authorization.
- Return stable machine-readable error codes. Do not return stack traces, SQL errors, provider secrets, or internal implementation details.
- Validate all values at the boundary, then enforce business invariants and authorization in the domain/service layer. Client validation is never trusted.
- Use `context.Context` for request-scoped database and provider calls. Bound pagination, query complexity, upload size, and execution time.
- Collection endpoints use cursor pagination. Do not offer arbitrary unbounded page sizes or client-controlled SQL sort expressions.
- Mutating operations that may be retried after a network failure must be naturally idempotent or accept an `Idempotency-Key` with a documented scope and retention period.

### Error envelope

All API errors use one envelope:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Some fields need attention.",
    "request_id": "req_01J...",
    "field_errors": [
      { "field": "display_name", "code": "TOO_LONG", "message": "Must be 60 characters or fewer." }
    ]
  }
}
```

`field_errors` is optional and appears only for safe, user-correctable field errors. The request ID must match a redacted server log entry. Keep user-facing messages stable enough for UI display; the frontend should branch on `code`, not parse `message`.

Recommended status mapping:

| HTTP | Use |
| --- | --- |
| `400` | Malformed request or invalid query syntax |
| `401` | Missing, expired, or invalid authentication |
| `403` | Authenticated but not permitted / account not eligible |
| `404` | Resource not found or intentionally concealed |
| `409` | State conflict, such as stale version or duplicate transition |
| `413` | Request/upload too large |
| `422` | Structurally valid request with field/business validation errors |
| `429` | Rate limit; include `Retry-After` when appropriate |
| `500` | Unexpected internal error with a generic message |
| `502` / `503` | Required upstream dependency unavailable / service not ready |

Use the status best aligned with the API's final convention and document it in OpenAPI. Do not return `200` with an error-shaped body.

## 6. Browser authentication and session contract

### Recommended approach

Use an opaque server-side session rather than exposing bearer or refresh tokens to browser JavaScript. Set a cookie such as `__Host-flingra_session` with `Secure`, `HttpOnly`, `Path=/`, no `Domain`, and an appropriate `SameSite` policy. Cookie lifetime, rotation, and revocation are server-controlled. Do not store credentials in local storage.

For cookie-authenticated state-changing requests, implement CSRF defenses. A practical pattern is a server-issued CSRF token returned by the session endpoint and echoed in an `X-CSRF-Token` header, plus strict `Origin`/`Referer` validation. Rotate the CSRF token with the session. Configure credentialed CORS only for the exact frontend origins; never combine credentials with wildcard origins.

If frontend and API are deployed on different sites and cookie policy cannot support this safely, make a documented architecture decision before switching to bearer tokens. Do not silently relax cookie or CORS settings.

### Account/session state

Return a server-owned account state that the frontend uses for routing:

```json
{
  "member_id": "mem_...",
  "account_state": "profile_incomplete",
  "contact_verified": true,
  "csrf_token": "..."
}
```

Suggested `account_state` values: `email_verification_required`, `age_review_required`, `age_rejected`, `gender_check_rejected`, `profile_incomplete`, `active`, `suspended`, `inactive_archived`. The server must reject protected operations unless the member is at least 21, email-verified, age-approved, gender check passed, profile/media requirements satisfied, and active, regardless of client route state.

Do not expose password hashes, session IDs, internal moderation flags, exact location, or other members' private data in session responses.

## 7. API endpoint contract

Paths and payloads in this section are proposed. Use the same names in OpenAPI, implementation, and frontend client. All successful responses are JSON except `204 No Content` operations.

### 7.1 Health and metadata

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /health/live` | None | Process is alive; no dependency checks |
| `GET /health/ready` | None/internal network | Ready to serve; check required dependencies with a short timeout |
| `GET /api/v1/meta` | None | Optional public API/version and feature flags; never return secrets or internal configuration |

Health endpoints must not expose environment variables, dependency versions with unnecessary detail, or diagnostic stack traces.

### 7.2 Registration, verification, login, and recovery

| Method and path | Auth | Success | Notes |
| --- | --- | --- | --- |
| `POST /api/v1/auth/register` | None | `202 Accepted` | Begin email/password registration; collect required emergency contact |
| `GET /api/v1/auth/google/start` | None | Redirect | Begin Google OIDC authorization with state and PKCE |
| `GET /api/v1/auth/google/callback` | OIDC state | `302` | Validate OIDC response and establish/continue account |
| `POST /api/v1/auth/email-verification/confirm` | Verification challenge | `200 OK` | Validate one-time code and advance account state |
| `POST /api/v1/auth/email-verification/resend` | Verification challenge | `202 Accepted` | Rate-limited; neutral response |
| `POST /api/v1/auth/login` | None | `200 OK` + session cookie | Generic credential failure; rate-limited |
| `GET /api/v1/auth/session` | Session cookie | `200 OK` | Current member state and CSRF token; `401` if no valid session |
| `POST /api/v1/auth/logout` | Session + CSRF | `204` | Revoke current session and expire cookie |
| `POST /api/v1/auth/password-reset-requests` | None | `202 Accepted` | Always neutral response |
| `POST /api/v1/auth/password-resets` | Reset token | `204` | Consume a short-lived, single-use token and revoke other sessions as policy defines |
| `POST /api/v1/auth/password` | Session + CSRF | `204` | Change password; require current password or recent re-authentication |

Example registration request:

```json
{
  "email": "member@example.test",
  "password": "user-supplied-secret",
  "date_of_birth": "1998-04-12",
  "gender": "female",
  "emergency_contact": {
    "name": "Trusted person",
    "phone_e164": "+2348012345678"
  },
  "terms_version": "terms-2026-01",
  "privacy_version": "privacy-2026-01",
  "marketing_opt_in": false
}
```

Account phone numbers are not supported. Email/password accounts must verify email; Google OIDC is an alternative sign-in method and only a provider-verified email may satisfy email verification. Emergency contact phone is separate from authentication and required at registration. The user attests the contact is trusted; the platform does not verify or notify the contact until a user-initiated emergency/trip-sharing action. Never store or log the raw password or verification code.

Date of birth is required. Members must be at least 21. Access to discovery and other member features stays disabled until an administrator reviews an accepted government document showing date of birth (for example, NIN, birth certificate, passport, or voter card) and the configured gender check passes. Store evidence encrypted and separately from profile data; retention/access policy must be approved before launch.

Registration returns a neutral response such as:

```json
{
  "status": "accepted",
  "next_step": "verify_email"
}
```

Login request:

```json
{
  "identifier": "member@example.test",
  "password": "user-supplied-secret"
}
```

The cookie is set via `Set-Cookie`; do not include the session secret in the JSON body.

Verification request:

```json
{
  "challenge_id": "ch_...",
  "code": "123456"
}
```

The challenge ID is an opaque, short-lived, limited-purpose identifier. The API returns the updated account state only after the operation is confirmed.

### Age and gender verification

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `POST /api/v1/me/age-verification/uploads` | Email-verified session + CSRF | Request a private upload for one accepted government document |
| `POST /api/v1/me/age-verification/submissions` | Session + CSRF | Submit document type and date-of-birth evidence for admin review |
| `GET /api/v1/me/verification-status` | Session | Read age-review and gender-check status without returning raw evidence |
| `GET /api/v1/admin/verification-queue` | Verification-reviewer role + MFA | List minimal review metadata |
| `POST /api/v1/admin/verification-queue/{id}/decision` | Reviewer role + MFA | Approve/reject age evidence and record reason/audit event |

Age proof may be a government-approved NIN image, birth certificate, passport, voter card, or other approved document that shows date of birth. Admin review must establish that the member is at least 21. Keep the document in restricted encrypted storage, separate from ordinary profile/media storage; never send it in an API response, logs, analytics, or ordinary Sentry events. Define reviewer access, retention/deletion schedule, encryption keys, and appeals before launch.

The product currently requires only `male` or `female` gender categories and requests face-based gender detection; a failed/mismatched automated result is rejected. This is a sensitive and error-prone biometric inference, not a reliable determination of a person's gender. Before launch, require a privacy/legal assessment, accuracy/bias testing across intended populations, user notice and appropriate consent, secure processing with minimal retention, and a documented support/appeal path for false rejections. Do not treat age-document review and face classification as interchangeable checks.

### 7.3 Current member and profile

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me` | Eligible session | Current member account state and safe settings summary |
| `GET /api/v1/me/profile` | Session | Own profile, including editable fields and review states |
| `PUT /api/v1/me/profile` | Session + CSRF | Create/replace profile fields; use only if complete replacement semantics are clear |
| `PATCH /api/v1/me/profile` | Session + CSRF | Partial update of explicitly supplied editable fields |
| `GET /api/v1/profiles/{profile_id}` | Eligible session | Public member profile, subject to visibility, block, and safety checks |

Use one consistent write method. `PATCH` is recommended for edits; omitted properties remain unchanged, while explicit `null` clears only documented nullable fields.

Required editable profile shape; optional public attributes remain product-configurable:

```json
{
  "display_name": "A member",
  "bio": "A short plain-text introduction.",
  "photo_ids": ["pho_...", "pho_...", "pho_..."],
  "video_ids": ["vid_...", "vid_..."],
  "public_attributes": {
    "interests": ["music", "food"]
  }
}
```

The response includes only fields visible to the requesting member, with moderation state for their own content:

```json
{
  "profile_id": "pro_...",
  "display_name": "A member",
  "bio": "A short plain-text introduction.",
  "photos": [
    { "photo_id": "pho_...", "url": "https://media.example.test/...", "status": "approved", "position": 0 }
  ],
  "public_attributes": { "interests": ["music", "food"] },
  "profile_state": "complete",
  "updated_at": "2026-11-13T12:00:00Z"
}
```

For another member's public profile, return a separate DTO that omits private fields and moderation details:

```json
{
  "profile_id": "pro_...",
  "display_name": "A member",
  "age_display": "30",
  "approximate_area": "Central district",
  "bio": "A short plain-text introduction.",
  "photos": [{ "url": "https://media.example.test/...", "position": 0 }],
  "public_attributes": { "interests": ["music"] }
}
```

Do not return email, emergency contact, exact date of birth, exact coordinates, private preference rules, report/block state, internal IDs, verification evidence, or staff notes. Public profile returns only age display (never DOB) and coarse location.

### 7.4 Discovery preferences and profile visibility

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me/discovery-preferences` | Eligible session | Read the member's private discovery and visibility settings |
| `PUT /api/v1/me/discovery-preferences` | Eligible session + CSRF | Replace preferences atomically |
| `GET /api/v1/discovery` | Eligible session | Return only eligible, mutually preference-compatible profiles |

Keep identity separate from preferences. Do not derive identity or preferences from each other. Do not expose these private settings on public profile responses.

Proposed preference shape; gender is restricted to `male` or `female`. Discovery preference is separate from identity:

```json
{
  "discover_genders": ["female"],
  "visible_to_genders": ["male"],
  "age_range": { "min": 25, "max": 40 },
  "max_distance_km": 50,
  "location_area_id": "area_..."
}
```

The controlled values are `male` and `female`. The product currently does not include a lesbian/orientation field. A member can separately choose one or both genders to discover and one or both genders allowed to discover them. Do not infer identity or preferences from photos or face analysis.

The server returns a discovery candidate only if all of these are true:

1. Both accounts meet eligibility and active-account policy.
2. Neither member has blocked the other, and no safety/moderation restriction excludes the result.
3. The candidate matches the viewer's selected discovery criteria.
4. The viewer is included in the candidate owner's visibility criteria.
5. Any required location/age constraints can be applied without disclosing exact sensitive values.

Example discovery request:

`GET /api/v1/discovery?limit=20&cursor=...&min_age=25&max_age=40&max_distance_km=50`

GPS permission is required for platform use. While a member is actively using the app, the client submits location updates to `PUT /api/v1/me/location`; the service uses precise coordinates only to calculate a coarse discovery area/distance and must never return exact coordinates to another member. Members may choose a separate discovery area to browse; that does not change or spoof their reported current location. Do not put precise coordinates in query strings, access logs, analytics, or referrer-bearing URLs. Do not continuously track in the background outside an explicitly active, consented safety trip. For the web client, background GPS updates are not guaranteed when the browser is closed or suspended; disclose that limitation.

Response:

```json
{
  "items": [
    {
      "profile_id": "pro_...",
      "display_name": "A member",
      "age_display": "30",
      "approximate_area": "Central district",
      "photos": [{ "url": "https://media.example.test/..." }],
      "bio_preview": "A short introduction."
    }
  ],
  "next_cursor": "opaque-cursor-or-null"
}
```

Cursor values are opaque, expiring, and bound to the query/session context as needed. The frontend must not fetch a broad set and filter incompatible members client-side.

### 7.5 Current location

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `PUT /api/v1/me/location` | Eligible session + CSRF | Submit current GPS fix while app is actively in use |
| `GET /api/v1/me/location-settings` | Session | Read permission/visibility state and selected discovery area |
| `PUT /api/v1/me/discovery-area` | Eligible session + CSRF | Set a manual search area without changing reported current location |

Example GPS update (never returned in discovery responses):

```json
{
  "latitude": 6.5244,
  "longitude": 3.3792,
  "accuracy_meters": 30,
  "captured_at": "2026-11-13T12:00:00Z"
}
```

Validate coordinate bounds, timestamp freshness, and accuracy. Do not treat GPS as proof of identity or safety. Store only a derived coarse cell for discovery unless a separately approved, time-limited trip-sharing feature needs exact location. Require explicit permission, explain how approximate location is used, and support pausing discoverability. When location permission is revoked or stale, stop returning the member in location-based discovery.

### 7.6 Profile photos and videos

Each active profile needs 3-10 approved photos and 2-10 approved profile videos, each no longer than 30 seconds. Proposed upload limits: 10 MB per photo and 100 MB per video; accept JPEG/PNG/WebP photos and MP4/WebM video, with server-side content detection. Do not accept arbitrary public URLs from clients.

All profile media must be private/quarantined until server moderation approves it. Use a constrained flow: request upload authorization, upload to private storage, finalize/scan/process server-side, then expose only approved derivatives. Enforce file size, detected content type, image/video decode, malware/content checks as appropriate, metadata stripping, and ownership checks. Keep raw uploads private. Reject or hold moderation-pending media; do not activate or list an incomplete profile.

Potential endpoints:

- `POST /api/v1/me/profile-photos/uploads` — request a short-lived, single-object upload authorization.
- `POST /api/v1/me/profile-photos` — finalize upload and start review.
- `PATCH /api/v1/me/profile-photos/order` — update order for owned photos.
- `DELETE /api/v1/me/profile-photos/{photo_id}` — remove an owned photo.
- `POST /api/v1/me/profile-videos/uploads` — authorize a short-lived private upload.
- `POST /api/v1/me/profile-videos` — finalize, process, and queue video moderation.
- `DELETE /api/v1/me/profile-videos/{video_id}` — remove an owned video.

When a member removes media, enforce the minimum media count before profile remains discoverable. Define URL expiry and retention/deletion handling for rejected media before launch.

### 7.7 Connection requests and messaging

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `POST /api/v1/profiles/{profile_id}/connection-requests` | Eligible session + CSRF | Male member requests connection with a female member |
| `GET /api/v1/me/connection-requests?direction=incoming&limit=20&cursor=...` | Session | List incoming or outgoing requests |
| `POST /api/v1/connection-requests/{request_id}/accept` | Female recipient + CSRF | Approve; opens a conversation |
| `POST /api/v1/connection-requests/{request_id}/decline` | Female recipient + CSRF | Reject; increments requester-to-recipient rejection count |

Only one pending request may exist for a member pair. Store every decision and enforce the three-rejection limit transactionally: after that specific female recipient has rejected the same male requester three times, reject future requests for the pair permanently. Do not expose rejection history to other members. The request sender and recipient receive an in-app notification; reject notification fan-out must not leak private details.

On approval, create/enable one conversation, but do not permit the recipient to send the first message. The requesting male must send the initial message; after that, both participants may message until blocked, account-restricted, or the connection is otherwise closed by policy. Every message request must verify conversation membership, connection state, participant eligibility, block state, size/rate limits, and moderation/abuse policy.

Potential messaging endpoints:

- `GET /api/v1/me/conversations?limit=20&cursor=...`
- `GET /api/v1/conversations/{conversation_id}/messages?limit=50&before=...`
- `POST /api/v1/conversations/{conversation_id}/messages` — sender must be the requester for the initial message.

Store messages as plain text in the first release unless attachment moderation and retention are specified. Realtime delivery is a transport layer; the database is authoritative. Use idempotency for message sends and never silently report a failed send as delivered.

### 7.8 Women-only live streams

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `POST /api/v1/live-streams` | Active, verified female member + CSRF | Create a live session and server-generated provider token |
| `GET /api/v1/live-streams?limit=20&cursor=...` | Eligible session | List live streams visible under discovery/visibility rules |
| `POST /api/v1/live-streams/{stream_id}/join` | Eligible male viewer + CSRF | Join and receive a short-lived viewer token |
| `POST /api/v1/live-streams/{stream_id}/end` | Stream owner + CSRF | End own stream |

Only approved female accounts may start a live stream; a server-side eligibility check is mandatory regardless of UI. Live sessions must use a reviewed provider/SFU, short-lived room tokens, participant limits, abuse reporting, moderation/termination controls, and audit events for staff actions. Do not record streams by default. Live streams are not specified as paid; do not charge for joining/hosting until product and provider terms explicitly say so.

### 7.9 Audio/video calls and call credits

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/call-credit-packs` | Public/member | List server-priced packs and terms |
| `POST /api/v1/call-credit-purchases` | Session + CSRF | Create provider checkout for a pack |
| `GET /api/v1/me/call-credit-balance` | Session | Show available/pending balance |
| `POST /api/v1/conversations/{conversation_id}/calls` | Connected member + CSRF | Request a call; peer must accept |
| `POST /api/v1/calls/{call_id}/accept` | Invited participant + CSRF | Accept; issue time-limited RTC credentials |
| `POST /api/v1/calls/{call_id}/end` | Participant + CSRF | End call |
| `GET /api/v1/me/call-credit-ledger` | Session | Read paginated member ledger |

Working price proposal from the concept brief: NGN 2,000 for 10 minutes, NGN 4,000 for 15 minutes, NGN 7,000 for 30 minutes. Treat these as server-configured draft prices, not final public rates, until unit economics, legal permissibility, provider terms, fees, refunds, and consumer disclosures are approved. Meter only server-confirmed connected call time. Show price, duration, cancellation/refund policy, and remaining credits before confirmation. If credits run out, stop the call or require an explicit extension purchase; never silently charge more. Fixed host rewards are deferred until fraud, payout, tax, and unit-economics policies are approved.

Use an idempotent append-only ledger for credit purchase, reservation, consumption, release, and refund. Validate provider webhooks. Never trust client-reported call duration, client payment status, or a call-provider token supplied by the browser.

### 7.10 Meetup invitations and held payments

Meetup-payment handling is a high-risk, legally gated feature. Every booking must include scheduled date, start time, expected duration, and location. The requester pays; funds remain with an approved payment provider until the meetup is marked complete and the requester confirms satisfactory service. There is no automatic release: confirmation enters a manual staff review/release queue. If there is no confirmation or a dispute, keep funds pending for staff review. Implement only through a licensed, provider-approved marketplace/settlement flow after written Nigerian legal advice and provider approval for this exact business model. Flingra must not hold customer funds in its ordinary operating account or call the service “escrow” without explicit legal authority.

Manual-only release policy selected: no automatic payout. A requester confirmation creates a release request for authorized staff/payment operations. If the requester does not confirm or a party disputes the transaction, funds remain pending for staff review under a published dispute process. Exact review SLA, refund criteria, recipient payout onboarding, fees, taxes, and permitted meetup categories must be approved before enabling payment.

Potential endpoints (contract and payment provider remain gated):

- `POST /api/v1/meetup-bookings` — create proposal with scheduled date, start time, duration, precise meeting location, and terms.
- `GET /api/v1/me/meetup-bookings?status=...&limit=...&cursor=...` — list own bookings.
- `GET /api/v1/meetup-bookings/{booking_id}` — read booking details for a participant only.
- `POST /api/v1/meetup-bookings/{id}/accept`, `/decline`, `/propose-changes`
- `POST /api/v1/meetup-bookings/{id}/payment` — initiate approved provider flow.
- `POST /api/v1/meetup-bookings/{id}/check-ins` — acknowledge a scheduled safety check-in.
- `POST /api/v1/meetup-bookings/{id}/complete` — each participant may record their own completion status.
- `POST /api/v1/meetup-bookings/{id}/requester-confirmation` — requester confirmation and manual staff release queue.
- `POST /api/v1/meetup-bookings/{id}/disputes` — open dispute; pauses release.
- `GET /api/v1/me/transactions` — safe transaction history.

Example booking proposal:

```json
{
  "booking_date": "2026-12-01",
  "scheduled_start": "2026-12-01T18:00:00Z",
  "timezone": "Africa/Lagos",
  "duration_minutes": 120,
  "location": {
    "label": "Agreed venue",
    "address": "Private exact location"
  },
  "terms": "Optional agreed details"
}
```

The exact location is never returned in discovery or public profile APIs. It is disclosed only to the two participants after both accept the booking, and to an emergency contact only after the member activates trip sharing or a missed-check-in escalation. Store access/audit events for access to the exact destination. Display times in the member's locale while the API stores UTC instants and the relevant timezone.

Booking state transitions must be explicit (`proposed`, `accepted`, `declined`, `cancelled`, `active`, `completed`, `disputed`). Both participants see booking date, start time, duration, and agreed location before acceptance; changes after acceptance require the other participant's renewed acceptance.

All payment state changes must be idempotent and derived from verified provider events plus audited staff decisions. Never release disputed funds automatically. Define dispute evidence, staff response SLA, refund criteria, recipient payout onboarding, fees, taxes, and permitted meetup categories before enabling this flow.

### 7.11 Notifications

Support in-app and push notifications. When a new female member completes required verification and becomes active, notify all active, eligible male accounts (in-app and push), unless the new female member opts out of this promotional event. Respect device/browser push permission; retain the in-app event according to the notification policy.

Connection request, approval/decline, new message, call request, live stream, payment state, moderation, and safety notifications must be event-driven and recipient-authorized. Do not include report details, exact location, private identity, or sensitive media in notification text. Deduplicate deliveries and record delivery status without logging payload secrets.

Potential endpoints:

- `GET /api/v1/me/notifications?limit=20&cursor=...`
- `POST /api/v1/me/notifications/{notification_id}/read`
- `PUT /api/v1/me/notification-settings` — including female profile-promotion opt-out and push token registration/removal.

### 7.12 Emergency contacts, booking check-ins, and safety activation

Emergency contact is required during signup and is a phone number separate from login. The submitted contact is not independently verified or notified during signup. The member must be told to enter a trusted contact and that it will be called only after an explicit SOS or a missed-check-in escalation. Before each booking's safety session starts, explain the one-minute prompts and automatic call after three missed acknowledgements. At activation/escalation, share only the information the member has been told about; record the consent and event. Do not promise emergency-service dispatch unless a staffed, tested process exists.

For each participant in an accepted booking, a durable scheduler begins check-in prompts every 1 minute from the agreed booking start until the agreed end or until the participant ends the safety session. Each acknowledgement must include the prompt ID so old/replayed responses cannot satisfy a later check-in. After 3 consecutive prompts receive no acknowledgement (about 3 minutes), automatically call that participant's emergency-contact number using an approved voice provider. The member can trigger SOS immediately without waiting for missed prompts. Treat location as approximate for member discovery; exact booking location may be shared only with booking participants and in an activated emergency flow.

Missed check-ins, failed delivery, and call outcomes must create auditable safety events. Prevent duplicate calls for the same escalation; expose a clear countdown/status to the member; let the member cancel a false alarm before dispatch where operationally safe. The emergency contact number is unverified, so delivery is best-effort and must not be represented as guaranteed. The check-in feature requires a staffed incident-response procedure and real-device testing before launch.

Suggested endpoints:

- `PUT /api/v1/me/emergency-contact` — set/update name and E.164 phone.
- `POST /api/v1/meetup-bookings/{booking_id}/safety-session` — start check-ins for an accepted booking.
- `POST /api/v1/meetup-bookings/{booking_id}/check-ins` — acknowledge the active prompt with `{ "prompt_id": "chk_..." }`.
- `POST /api/v1/meetup-bookings/{booking_id}/safety-session/end` — stop check-ins when the booking/safety session ends.
- `POST /api/v1/safety/activations` — explicit immediate SOS with selected action and consent.
- `GET /api/v1/me/safety-activations` — member's own event/status history.

### 7.13 Blocking

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me/blocks?limit=20&cursor=...` | Session | List accounts blocked by the current member |
| `PUT /api/v1/me/blocks/{member_id}` | Session + CSRF | Idempotently block a member |
| `DELETE /api/v1/me/blocks/{member_id}` | Session + CSRF | Unblock a member |

Blocking must immediately affect discovery and any future contact surfaces in both directions according to documented product behavior. A member must not learn who blocked them. Check for self-block, duplicates, deleted accounts, race conditions, and authorization. The frontend may show a confirmation; the server decides the resulting relationship state.

### 7.14 Reporting and moderation

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/report-reasons` | Session or public | Return current report categories and safe labels |
| `POST /api/v1/reports` | Session + CSRF | Submit a report against a member or supported content |

Example:

```json
{
  "target_type": "profile",
  "target_id": "pro_...",
  "reason_code": "harassment",
  "description": "Optional plain-text context.",
  "also_block": true
}
```

Response should confirm receipt without exposing moderation outcome:

```json
{
  "report_id": "rep_...",
  "status": "received",
  "received_at": "2026-11-13T12:00:00Z"
}
```

Restrict report details to authorized moderation staff and the reporting workflow. Do not expose report existence/details to the reported member. Redact descriptions from ordinary logs and monitoring. Duplicate submission should be safely handled; use an idempotency key or a defined duplicate policy. Evidence uploads are out of scope until storage, access, retention, and review controls are agreed.

### Staff/admin API boundary

Staff operations use a separately authenticated `/api/v1/admin` surface or separate admin host, require MFA, least-privilege roles, CSRF protection if cookie-based, and an append-only audit event for every sensitive read/decision. Never grant every administrator access to every evidence type.

Required first-release staff queues/actions include age-document review, media approval/rejection, reports, missed-check-in safety incidents, payment release/dispute review, and restoration applications. Examples:

- `GET /api/v1/admin/media-review-queue`; `POST /api/v1/admin/media/{id}/decision`
- `GET /api/v1/admin/reports`; `POST /api/v1/admin/reports/{id}/decision`
- `GET /api/v1/admin/safety-incidents`; `POST /api/v1/admin/safety-incidents/{id}/decision`
- `POST /api/v1/admin/meetup-payments/{id}/release`; `POST /api/v1/admin/meetup-payments/{id}/refund`

Reviewer views must be purpose-limited and masked. Identity reviewers access age evidence; safety staff access relevant incidents; payment staff access ledger/dispute data. Admin access, export, and decisions must be logged with actor, reason, target, time, and request ID.

### 7.15 Account settings and contact

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me/settings` | Session | Safe account settings, masked contact, and account state |
| `POST /api/v1/me/contact-change-requests` | Session + CSRF | Start changing contact; must re-verify the new contact |

### 7.16 Account deactivation and restoration

The user-facing “delete account” action is a soft deactivation request: immediately set the account to `inactive_archived`, revoke sessions, remove the profile from discovery/live lists, prevent new connections/messages/calls/payments, and move or logically isolate the account and related records in an archive. Do not permanently delete user details under the current product decision.

Restoration requires a written application and an authorized admin decision; do not allow self-service restore. Reinstatement must restore only eligible records, re-run account/safety restrictions, and audit the staff action.

Potential endpoints:

- `POST /api/v1/me/deactivation-requests` — confirm and deactivate account.
- `POST /api/v1/me/restoration-applications` — submit restoration request from an inactive account flow.
- Staff-only `GET /api/v1/admin/restoration-applications` and `POST /api/v1/admin/restoration-applications/{id}/decision`.

The no-permanent-deletion requirement and indefinite archival are not launch-ready until Nigerian privacy counsel defines lawful basis, retention periods, data-subject rights, backups, financial records, and any deletion obligations. Do not promise users indefinite retention or implement permanent erasure contrary to law; make this a written legal go/no-go.

## 8. Data model boundaries

This is a conceptual model, not a final schema. Use opaque IDs in API responses and foreign keys internally. Keep sensitive data separated logically and restrict query access.

| Concept | Typical data | Security notes |
| --- | --- | --- |
| Member/account | ID, normalized contact, password hash, eligibility/account state, accepted policy versions | Contact and credential material are private; unique constraints on normalized identifiers |
| Session | Hashed session secret, member ID, expiry, creation/revocation metadata | Store only a one-way hash of the cookie secret; never log it |
| Profile | Display name, bio, `male`/`female` category, public selected fields, moderation state | Separate public response projection from owner view |
| Verification evidence | Document object, DOB review state, face-check decision, reviewer/audit metadata | Highly sensitive; encrypted isolated storage, strict reviewer access and approved retention |
| Discovery preferences | Discover genders, visible-to genders, filters | Private; update atomically; use in server-side candidate selection |
| Location | Latest GPS-derived coarse cell, selected search area, captured time/accuracy | Never return exact coordinates; minimize precise fix retention; discovery only while active |
| Media metadata | Owner, storage key, type, status, order, duration, derivative references | Raw uploads quarantined; approved derivative only; no public bucket/client-chosen key |
| Block | Blocker, blocked member, timestamp | Unique pair; apply consistently in all relevant queries |
| Report | Reporter, target, reason, restricted description, status/timestamps | High sensitivity; staff-only access and audited reads/actions |
| Connection request | Requester, recipient, state, rejection count, timestamps | Enforce maximum three rejections per pair transactionally |
| Conversation/message | Connection, participants, plain-text message, moderation state, timestamps | Participant-only access; requester sends first message; rate-limit and audit safety events |
| Live/call session | Provider room/session reference, participants, state, authoritative metering | Short-lived provider tokens; do not record by default; never trust client duration |
| Credit/payment ledger | Member, amount/currency, transaction type, provider reference, state | Append-only/idempotent; reconcile provider webhooks; no card data |
| Booking/check-in | Participants, date/time/duration, exact location, booking state, check-in deadlines | Exact destination restricted to participants; missed prompts trigger audited escalation |
| Emergency contact | Member, name, phone, added/updated timestamps | Required, unverified; call only by explicit SOS or defined missed-check-in escalation |
| Notification | Recipient, event type, read/delivery state, safe payload | No sensitive report/location data in payload; deduplicate pushes |
| Archived member | Member reference, archived profile/account data, restoration state | Hidden/inactive; restoration requires staff decision; retention is legally gated |

Use explicit foreign keys, uniqueness constraints, indexes for actual query patterns, and transactions for related state changes. Avoid embedding unbounded histories or sensitive evidence in a member row. Never use a public API DTO as a database schema.

## 9. Authentication, authorization, and privacy rules

- Hash passwords with Argon2id through a maintained Go implementation, with parameters reviewed and versioned. Support rehash-on-login if parameters are upgraded.
- Store opaque session secrets only as one-way hashes. Rotate sessions on authentication/security-sensitive transitions; revoke on logout, password reset, account suspension, and other defined events.
- Add CSRF protection for cookie-authenticated mutations and strict origin checks. Set exact CORS origins, methods, and headers.
- Rate-limit signup, login, verification, recovery, report submission, and any expensive discovery/query routes. Use account- and network-aware abuse controls without permanently locking out legitimate users.
- Avoid account enumeration in signup, login, verification resend, and recovery flows.
- Enforce eligibility, role, ownership, and object-level authorization on every operation. Use deny-by-default middleware, then domain-level checks where resource relationships matter.
- Keep account identity, profile identity, discovery preferences, and visibility controls distinct in data and authorization logic.
- Minimize personal data, define retention and deletion, and restrict staff access. Treat location, reports, identity data, messages, and payment metadata as sensitive.
- Never store payment card data. Verify signed webhooks and use idempotency for all payment/call-credit and meetup-payment operations.
- Redact passwords, cookies, tokens, OTPs, precise location, report/message text, and sensitive profile values from logs, traces, and error monitoring.
- Keep secrets out of source, local committed config, logs, images, and CI artifacts. Use separate environment credentials and managed secret injection.

## 10. Database and migration practices

- Use `database/sql` with context-aware queries and a bounded connection pool. Set connection lifetimes and pool limits intentionally.
- Use placeholders for values. Allowlist dynamic identifiers such as sort fields; never concatenate user values into SQL.
- Keep transactions short. Set isolation/locking expectations for operations such as account creation, blocking, and one-time token consumption.
- Name migrations in order, review SQL, test forward migration from the prior schema, and document a rollback or forward-recovery plan.
- Prefer expand/contract migrations for changes deployed independently from application versions.
- Do not run destructive migrations automatically in API startup.
- Use least-privilege database credentials; runtime users should not have schema-admin privileges.
- Back up production data and regularly test restore procedures. Encrypt backups and restrict their access/retention.

## 11. Provider and background-work boundaries

Wrap external dependencies behind narrow interfaces. Never call a vendor directly throughout domain code.

- Set explicit HTTP timeouts; propagate request contexts and deadlines.
- Retry only transient failures with bounded attempts/backoff. Do not retry non-idempotent operations without idempotency protections.
- Treat provider responses/webhooks as untrusted. Verify signatures and expected event/account identifiers.
- Make external workflows explicit (`pending`, `confirmed`, `failed`, etc.); do not claim success before confirmation.
- If adding workers, define job idempotency, bounded retries, dead-letter/terminal failure handling, monitoring, and safe replay.
- No payment, SMS, maps, push, media storage, or verification provider is selected by this scaffold. Confirm regional availability, privacy terms, cost, and operational support before adoption.

## 12. Configuration and runtime

Validate required configuration once at startup and fail fast with a clear, redacted error. Avoid insecure defaults.

Proposed configuration categories:

- HTTP bind address, read/header/write/idle timeouts, max request size.
- Exact allowed frontend origins and cookie security/SameSite settings.
- MySQL DSN from secret injection, pool size, connection timeout.
- Session secret/hash configuration and session lifetimes.
- Rate-limit settings and trusted proxy configuration.
- Log level/format, monitoring DSN, and environment name.
- Provider credentials only when a provider is actually enabled.

Never trust forwarded client IP headers unless requests come through an explicitly configured trusted proxy. Expose liveness and readiness separately. Gracefully stop accepting requests and close dependencies on shutdown.

## 13. Testing and quality gates

### Unit tests

- Domain validation, account state transitions, preference matching, and eligibility.
- Bidirectional discovery visibility logic, including multiple preferences and empty selections.
- Authorization/ownership and block/report rules.
- Password/session token lifecycle and one-time challenge expiry.

### HTTP/API tests

- Request decoding, body limits, error envelope/status mapping, cookie settings, CSRF, CORS, and rate limits.
- Every endpoint's success and failure schema against OpenAPI.
- Generic responses for account recovery and authentication failure.
- No sensitive fields in public profile, session, or discovery DTOs.

### Integration tests

- Run migrations against an empty database and upgrade from the previous schema.
- Exercise MySQL constraints, transactions, concurrent/idempotent operations, and discovery queries.
- Use disposable databases/containers; never point tests at production.

### Required security cases

- Unauthenticated requests and expired/revoked sessions.
- Cross-account object access and attempts to edit another member's profile.
- Mutations without valid CSRF/origin checks.
- Suspended, ineligible, or incomplete members attempting protected features.
- Both directions of blocking suppressing discovery as intended.
- Candidate excluded by either member's preferences, account state, or safety rules.
- Fourth request after three recipient rejections is denied; an accepted request opens chat but blocks recipient messaging until the requester sends first.
- Only verified female members can start a live stream; a male viewer receives only a short-lived participant token.
- Every one-minute check-in and third-missed-prompt emergency call is idempotent and restricted to the active booking window.
- An emergency contact is never called at signup; only explicit SOS or the configured missed-check-in escalation can initiate contact.
- Payment release requires requester confirmation plus audited staff action; no automatic release or unverified client payment status.
- Soft-deactivated accounts disappear from discovery/live/connection endpoints and restoration requires authorized review.
- Oversized/malformed input and rate-limited abuse flows.
- Log/monitoring redaction assertions for credentials and sensitive content.

Run formatting (`gofmt`), static analysis/vet, unit and integration tests, migration checks, and OpenAPI lint/validation in CI. Add race detection for relevant packages when practical. Pin tooling versions in CI rather than relying on a developer's global setup.

## 14. Frontend integration checklist

Before handing an endpoint to the frontend developer:

1. Add or update the OpenAPI operation, schemas, auth requirements, status codes, and examples.
2. Implement request/response DTOs and stable error codes.
3. Confirm cookie, CSRF, CORS, and credentialed-fetch settings in the target environments.
4. Document whether fields are public, owner-only, or staff-only; omit private fields from the response rather than asking the frontend to hide them.
5. Include loading-relevant states in responses (for example `account_state`, `profile_state`, moderation state) where the UI must route or render differently.
6. Add handler/domain/DB tests and contract tests.
7. Provide a sanitized example request/response and known error cases.

Frontend requests must send cookies (`credentials: "include"` or Axios `withCredentials: true`) and the CSRF header for state-changing requests. The frontend must not receive session bearer secrets, decide age/eligibility, implement discovery compatibility by itself, or treat a `2xx` as completion for a pending external workflow.

## 15. Local development status

There is no Go module, API, database config, or runnable command yet. During bootstrap:

- Add `go.mod` and pin the Go toolchain.
- Add a `.env.example` containing placeholder values only; local `.env` remains ignored.
- Add Docker Compose only if it helps start a local MySQL instance repeatably.
- Document verified commands for setup, migrations, API run, formatting, lint/vet, unit tests, and integration tests.
- Keep local test accounts and all fixtures synthetic.

Do not publish commands as working until they have been run successfully against the scaffold.

## 16. Confirmed product decisions and launch gates

### Confirmed by product owner

- One shared app; no separate gender-based apps. Supported account gender values are `male` and `female`; do not add a sexual-orientation/lesbian field. Discovery and visibility choices are separate from gender.
- Minimum age is 21. Signup is email/password with verified email or Google sign-in. Account phone sign-in is not allowed.
- Date of birth and government-approved proof are required; admin reviews age proof. Face-based gender detection is requested and a mismatch is automatically rejected.
- Emergency contact name and phone are required at signup, are not verified/notified then, and are contacted only after explicit SOS or the missed-check-in trigger.
- Profile has 3-10 photos and 2-10 videos, each video at most 30 seconds; default upload caps are 10 MB/photo and 100 MB/video. Server moderation must approve every item before public display.
- GPS permission is required while using the app. Discovery shows approximate location only; a manual discovery-area choice is separate from actual location.
- Male member requests connection with female member. Female member approves or declines. After three rejections by the same recipient, that requester cannot try that recipient again. On approval, messaging opens, but requester must send the first message.
- Only verified/eligible female accounts can start live streams.
- On a new female profile becoming active, notify all active/eligible male accounts in-app and by push unless she opts out.
- Launch scope includes in-app messaging, calls/call credits, lives, verification, notifications, and meetup bookings/payments, subject to legal and provider go/no-go review.
- Call pricing is still a draft from the concept document (NGN 2,000/10 min; NGN 4,000/15 min; NGN 7,000/30 min); fixed host rewards and VIP/VVIP are deferred.
- Meetup payment release is manual only after the requester confirms satisfactory completion. If not confirmed or disputed, funds stay pending staff review; no automatic release.
- Booking requires date, start time, duration, and location. Check-ins prompt every minute during the accepted booking; after three consecutive unanswered prompts, call the emergency contact. User SOS is available immediately.
- Account deletion is soft deactivation/archive; profile becomes inactive/invisible, and restoration requires an application and staff decision. Product requests no permanent deletion of user details.

### Must be resolved before production

1. Written Nigerian legal/privacy review for 21+ eligibility, government ID processing, face-based gender inference, mandatory GPS, promotional notifications, archived accounts, calls/live, and meetup payments.
2. Privacy impact, retention and access policy for identity documents, biometric processing, precise GPS fixes, call/check-in events, emergency contacts, and archived personal data. Do not promise indefinite retention unless counsel approves.
3. Accuracy/bias testing and a support appeal process for automated gender-check rejection. Do not treat face classification as reliable proof of identity.
4. Written payment-provider approval for call credits, the exact meetup payment/hold/release flow, marketplace payouts, refunds, and disputes. Funds must remain with an approved provider; never hold customer money in Flingra's operating account.
5. Final prices, credit expiry/refund rules, call extension behavior, meetup fee/payout/review policies, and dispute staff SLA.
6. Exact location update/expiry behavior, browser permission limitations, trusted operational coverage for three missed check-ins, and emergency-call provider/failure escalation.
7. Supported Google OIDC setup, payment/RTC/push/SMS providers, frontend/API origins, production CORS/cookie settings, and deployment topology.
8. File-format detection, moderation policy and reviewer workflow; proposed supported photo/video formats and caps must be tested with actual deployment/provider constraints.

Until gates are met, keep sensitive or regulated features behind configuration flags and fail closed. Do not silently interpret missing or invalid preference data as permission to expose a profile, release money, or contact an emergency contact.
