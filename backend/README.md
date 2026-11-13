# Flingra backend implementation and API contract

## 1. Purpose and status

This is the backend developer's implementation guide and the frontend team's proposed integration contract. It describes the Go service, core domain boundaries, HTTP behavior, endpoint inventory, example payloads, and security/operational requirements.

The repository is currently a scaffold: no API, Go module, database schema, OpenAPI file, or provider integration exists yet. The endpoints and JSON below are proposed contracts to implement and then capture in the OpenAPI specification. Resolve the product decisions in §16 before freezing affected schemas. Once implementation begins, the OpenAPI document and tests—not prose examples—must be the source of truth.

Flingra is one application for all eligible adults. Discovery preferences and profile visibility are separate, user-controlled concepts; they are not inferred from identity. See the [system blueprint](../docs/architecture.md) and [frontend specification](../frontend/README.md).

## 2. Backend goals and first-release scope

Build a secure, reliable modular monolith that supports:

- Account registration, sign-in, contact verification if required, session management, and password recovery.
- Eligibility and onboarding state enforcement.
- Member-owned profile management and public profile presentation.
- Server-filtered discovery based on eligibility, safety rules, and compatible viewer/owner preferences.
- Blocking, reporting, account privacy/deletion requests, and a restricted moderation workflow.
- Operational health, structured redacted logs, and observable failures.

Messaging, payments, identity verification, notifications, live calls, and background processing are later modules unless separately approved. Do not create tables, endpoints, or vendor dependencies for hypothetical features.

## 3. Proposed stack

- **Language:** Go; pin the supported Go toolchain in `go.mod`, CI, and the container image once the application is bootstrapped.
- **HTTP:** Standard library `net/http` and `ServeMux` initially. Adopt a focused router only if routing complexity warrants it.
- **Contract:** OpenAPI 3.x, checked into `backend/api/openapi.yaml`. Use it for review, frontend types/client generation if adopted, and API contract tests.
- **Database:** MySQL 8.4 LTS through `database/sql` and a maintained MySQL driver. Keep SQL parameterized; consider `sqlc` after the team agrees on the query workflow.
- **Migrations:** Ordered SQL migration files run as an explicit deployment step using a selected migration tool. Do not auto-run schema changes on every API startup.
- **Testing:** Go `testing`, `httptest`, and integration tests against disposable MySQL.
- **Operations:** Docker, GitHub Actions, health/readiness endpoints, structured logs, and Sentry or an equivalent error-monitoring provider.

Keep the initial service synchronous and single-deployable. Add Redis, a job worker, WebSockets, or provider SDKs only for a defined use case.

## 4. Suggested Go layout

```text
backend/
  cmd/api/                  # process entry point and dependency wiring
  internal/
    auth/                   # credentials, sessions, verification
    member/                 # member lifecycle and eligibility state
    profile/                # profile editing and public profile view
    discovery/              # preferences and eligible candidate selection
    safety/                 # blocks, reports, staff moderation boundary
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

Suggested `account_state` values: `contact_verification_required`, `eligibility_review_required`, `profile_incomplete`, `active`, `suspended`, `deletion_pending`. Finalize names before OpenAPI generation. The server must reject protected operations unless the member is eligible and active, regardless of client route state.

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
| `POST /api/v1/auth/register` | None | `202 Accepted` | Begin registration; neutral response to reduce account enumeration |
| `POST /api/v1/auth/contact-verification/confirm` | Verification challenge | `200 OK` | Validate a one-time code and advance account state |
| `POST /api/v1/auth/contact-verification/resend` | Verification challenge | `202 Accepted` | Rate-limited; response must not reveal account existence |
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
  "phone_e164": null,
  "password": "user-supplied-secret",
  "terms_version": "terms-2026-01",
  "privacy_version": "privacy-2026-01",
  "marketing_opt_in": false
}
```

At least one contact method is required. Collect age or age-assurance information only after the age policy and provider/legal requirements are decided; do not imply that a browser checkbox proves eligibility. Never store or log the raw password or verification code.

Registration returns a neutral response such as:

```json
{
  "status": "accepted",
  "next_step": "check_contact"
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

### 7.3 Current member and profile

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me` | Eligible session | Current member account state and safe settings summary |
| `GET /api/v1/me/profile` | Session | Own profile, including editable fields and review states |
| `PUT /api/v1/me/profile` | Session + CSRF | Create/replace profile fields; use only if complete replacement semantics are clear |
| `PATCH /api/v1/me/profile` | Session + CSRF | Partial update of explicitly supplied editable fields |
| `GET /api/v1/profiles/{profile_id}` | Eligible session | Public member profile, subject to visibility, block, and safety checks |

Use one consistent write method. `PATCH` is recommended for edits; omitted properties remain unchanged, while explicit `null` clears only documented nullable fields.

Suggested editable profile shape (exact optional attributes are a product decision):

```json
{
  "display_name": "A member",
  "bio": "A short plain-text introduction.",
  "photo_ids": ["pho_..."],
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

Do not return email, phone, date of birth, exact coordinates, private identity fields, preference rules, report/block state, internal IDs, verification evidence, or staff notes. The public age/location representation remains subject to product/legal approval.

### 7.4 Discovery preferences and profile visibility

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me/discovery-preferences` | Eligible session | Read the member's private discovery and visibility settings |
| `PUT /api/v1/me/discovery-preferences` | Eligible session + CSRF | Replace preferences atomically |
| `GET /api/v1/discovery` | Eligible session | Return only eligible, mutually preference-compatible profiles |

Keep identity separate from preferences. Do not derive identity or preferences from each other. Do not expose these private settings on public profile responses.

Proposed preference shape; controlled vocabulary and semantics require product approval:

```json
{
  "discover_audiences": ["women"],
  "visible_to_audiences": ["men", "women"],
  "age_range": { "min": 25, "max": 40 },
  "max_distance_km": 50,
  "location_area_id": "area_..."
}
```

Audience keys are examples only. Use stable server-defined values, validate allowed combinations, and support multiple selections. If inclusive/custom identity or audience choices are offered, define their matching semantics explicitly instead of using free-form values as hidden authorization rules.

The server returns a discovery candidate only if all of these are true:

1. Both accounts meet eligibility and active-account policy.
2. Neither member has blocked the other, and no safety/moderation restriction excludes the result.
3. The candidate matches the viewer's selected discovery criteria.
4. The viewer is included in the candidate owner's visibility criteria.
5. Any required location/age constraints can be applied without disclosing exact sensitive values.

Example discovery request:

`GET /api/v1/discovery?limit=20&cursor=...&min_age=25&max_age=40&max_distance_km=50`

Location should use an approved coarse area or short-lived server-side location input. Never return exact coordinates. Do not put precise location in query strings, access logs, analytics, or referrer-bearing URLs.

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

### 7.5 Profile photos

Profile photos are dependent on a media/security decision and may be deferred. Do not accept arbitrary public URLs from clients.

If enabled, use a constrained flow: request upload authorization, upload to private/quarantine storage, finalize/scan/process server-side, then expose only approved derivatives. Enforce file size, detected content type, image decode, malware/content checks as appropriate, metadata stripping, and ownership checks. Keep raw uploads private.

Potential endpoints:

- `POST /api/v1/me/profile-photos/uploads` — request a short-lived, single-object upload authorization.
- `POST /api/v1/me/profile-photos` — finalize upload and start review.
- `PATCH /api/v1/me/profile-photos/order` — update order for owned photos.
- `DELETE /api/v1/me/profile-photos/{photo_id}` — remove an owned photo.

Define allowed formats, maximum count/size/dimensions, URL expiry, moderation states, and deletion behavior before frontend integration.

### 7.6 Blocking

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me/blocks?limit=20&cursor=...` | Session | List accounts blocked by the current member |
| `PUT /api/v1/me/blocks/{member_id}` | Session + CSRF | Idempotently block a member |
| `DELETE /api/v1/me/blocks/{member_id}` | Session + CSRF | Unblock a member |

Blocking must immediately affect discovery and any future contact surfaces in both directions according to documented product behavior. A member must not learn who blocked them. Check for self-block, duplicates, deleted accounts, race conditions, and authorization. The frontend may show a confirmation; the server decides the resulting relationship state.

### 7.7 Reporting and moderation

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

Staff moderation endpoints are not part of the member API contract. Before launching user-generated content at scale, define a separate staff authorization model, least-privilege roles, audit trail, review states, escalation, and retention.

### 7.8 Account settings, privacy, and deletion

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/me/settings` | Session | Safe account settings, masked contact, and account state |
| `POST /api/v1/me/contact-change-requests` | Session + CSRF | Start changing contact; must re-verify the new contact |
| `POST /api/v1/me/deletion-requests` | Session + CSRF, recent re-auth as policy requires | Request account deletion |
| `GET /api/v1/me/deletion-request` | Session | Read deletion request state if one exists |
| `DELETE /api/v1/me/deletion-request` | Session + CSRF | Cancel only when policy allows |

Deletion request example:

```json
{
  "confirm": true,
  "reason_code": "prefer_not_to_say"
}
```

Return explicit status, effective date/grace period if applicable, and a user-safe explanation. Do not promise immediate erasure unless every affected store/provider and legal retention rule supports it. Define retention, backups, legal holds, and de-identification behavior before implementation.

### 7.9 Deferred feature APIs

Do not implement these until product approval and safety/operational requirements are defined:

- Connections/likes/matching and messaging.
- Payments, refunds, and provider webhooks.
- Identity verification and evidence lifecycle.
- Push/email/SMS preference centers.
- Calls/LiveKit and real-time events.

Each needs a reviewed contract, abuse/security model, provider failure handling, data retention decision, and frontend states before its routes are added.

## 8. Data model boundaries

This is a conceptual model, not a final schema. Use opaque IDs in API responses and foreign keys internally. Keep sensitive data separated logically and restrict query access.

| Concept | Typical data | Security notes |
| --- | --- | --- |
| Member/account | ID, normalized contact, password hash, eligibility/account state, accepted policy versions | Contact and credential material are private; unique constraints on normalized identifiers |
| Session | Hashed session secret, member ID, expiry, creation/revocation metadata | Store only a one-way hash of the cookie secret; never log it |
| Profile | Display name, bio, public selected fields, moderation state | Separate public response projection from owner view |
| Discovery preferences | Viewer audiences, visibility audiences, filters | Private; update atomically; use in server-side candidate selection |
| Coarse location | Area or derived coarse cell, consent/update metadata | Avoid storing precise coordinates unless strictly required; define retention |
| Photo metadata | Owner, storage key, status, order, derivative references | Raw file private/quarantined; no public bucket or client-chosen storage key |
| Block | Blocker, blocked member, timestamp | Unique pair; apply consistently in all relevant queries |
| Report | Reporter, target, reason, restricted description, status/timestamps | High sensitivity; staff-only access and audited reads/actions |
| Deletion request | Member, state, requested/effective timestamps | Track fulfillment across systems and providers |

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
- Never store payment card data. Verify signed webhooks and use idempotency if payments are later added.
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

## 16. Product/API decisions required before contract freeze

These are not safe to guess in backend code:

1. Signup identifier rules: email, phone, or either; contact verification requirements and delivery provider.
2. Age eligibility/assurance approach, minimum age policy, and data retention.
3. Identity options, audience vocabulary, and exact compatibility semantics for discovery and visibility.
4. Whether empty visibility preferences mean “nobody,” “not configured,” or another explicit state.
5. Public age/location representation and whether manual coarse location is supported.
6. Required versus optional profile fields and photo moderation/limits.
7. Whether connections/likes, messaging, payments, verification, notifications, or calls are in the first release.
8. Account deletion timing, grace period, legal retention, export requirements, and backup erasure policy.
9. Production frontend/API origins and deployment topology, which determine cookie/CORS settings.

Until decided, represent uncertain values explicitly and fail closed for access decisions. Do not silently interpret missing or invalid preference data as permission to expose a profile.
