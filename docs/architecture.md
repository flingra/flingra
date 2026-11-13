# Flingra system blueprint

## Purpose and status

Flingra is a proposed Nigeria-first platform for consenting adults aged 21 or older to discover connections, communicate, and plan meetups. Safety, privacy, and trust are foundational product requirements.

This repository is currently a scaffold. This blueprint captures a practical direction for implementation; it is not evidence that features, controls, providers, or compliance obligations are already in place. Validate applicable Nigerian and other launch-market laws, payment rules, and data-protection obligations with qualified counsel before launch.

## Product principles

1. **Adults and consent first.** The current minimum age is 21. Require email verification, government age-proof review, clear consent, user control, and prompt safety response before enabling discovery or messaging.
2. **Safety is a core workflow.** Users need accessible block, report, and support actions. Moderation needs restricted access, review records, and a documented escalation process.
3. **Privacy by default.** Collect the minimum data needed, explain its use, limit access and retention, provide the confirmed soft-deactivation flow, and meet applicable data-subject rights.
4. **Trust without overclaiming.** Verification signals must explain what was and was not checked; verification is not a guarantee of identity, safety, or conduct.
5. **Ship a narrow, reliable first release.** Defer costly integrations and real-time features until product value, safety readiness, and operational ownership are established.

## One shared member experience

Flingra is planned as one application, with male/female account categories only; a sexual-orientation field is not in the current scope. Members should configure who they want to discover separately from who may discover them. Identity is not a proxy for those preferences, and face-check evidence remains private.

Discovery must be filtered server-side: a profile is eligible to appear only when it meets the viewer's discovery preferences and the profile owner's visibility preferences, in addition to account eligibility and safety rules. The current connection flow is male requester to female recipient, with approval required before messaging.

The male/female category and connection behavior are product requirements, but the face-based gender check is an error-prone biometric inference. Accuracy, bias, privacy, consent, retention, and false-rejection appeal handling require specialist review before launch.

## Proposed first release

The current intended launch scope includes:

- Email/password and Google sign-in, 21+ checks, government document age review, profile and media moderation.
- GPS-required discovery that returns approximate location only; a distinct user-selected search area.
- Male-to-female connection requests, female approval/decline, requester-first messaging, and block/report.
- Female-only live streams, accepted audio/video calls, call credits, in-app/push notifications, and required emergency contact.
- Meetup bookings with date/time/duration/location, one-minute safety check-ins, SOS, and provider-held payment subject to legal/provider approval.
- Admin tools for age/media verification, moderation, safety incidents, payment review, and archived-account restoration.

These features add substantial biometric, location, payment, safeguarding, and operational risk. Written legal/privacy assessment, provider acceptance, staffed incident response, and tested controls are production go/no-go items.

## High-level architecture

```text
Browser
  └── React + TypeScript web client
        └── HTTPS API
              └── Go modular monolith (HTTP API)
                    ├── MySQL: accounts, profiles, bookings, ledgers, safety events
                    ├── Durable workers: media moderation, notifications, check-in timers
                    └── Provider adapters: payment, push/voice, identity, media, RTC
```

Keep the API as the authority for identity, authorization, validation, and business rules. Use a modular monolith initially; separate services only when measured scale, isolation, or team ownership benefits exceed the added deployment and security complexity.

## Proposed stack

| Concern | Recommendation | Use when |
| --- | --- | --- |
| Web application | React, TypeScript, Vite | Core client |
| UI and navigation | Tailwind CSS, shadcn/ui, React Router | Consistent responsive interface |
| Client data/forms | TanStack Query, React Hook Form, Zod | API state, form state, immediate feedback |
| Shared client state | Zustand | Only cross-route client state not owned by URL, form, or server cache |
| API | Go, standard `net/http` library, OpenAPI contract | Small HTTP API with minimal framework/runtime dependencies |
| Persistence | MySQL 8.4 LTS, Go SQL driver, versioned SQL migrations | Durable relational data and controlled schema changes |
| Tests | Vitest, Playwright, Go `testing` package | Client units/components, user journeys, backend rules/APIs |
| Delivery/operations | Docker, GitHub Actions, Sentry | Repeatable builds, CI, error visibility |

Durable background processing is required for media moderation, push delivery, provider webhooks, and scheduled booking check-ins; Redis itself is optional. RTC/live streaming, payment, push/voice, verification, and media storage providers are needed for the stated launch scope but are not selected yet. Choose each after confirming regional availability, privacy and contractual terms, cost, reliability, legal acceptance, and tested failure paths.

## Shared security baseline

- Enforce HTTPS. Keep secrets server-side and use managed secret injection; rotate credentials and separate development, test, and production environments.
- Use Argon2id for password hashes. For browser authentication, prefer secure, `HttpOnly`, appropriately `SameSite` cookies with short-lived sessions, refresh rotation/revocation, CSRF defenses, and rate-limited login and recovery flows.
- Authorize every protected operation on the server and deny by default. Apply least privilege to staff, service accounts, and database users; audit sensitive moderation and administrative actions.
- Validate inputs at API boundaries, bound request sizes and pagination, and use parameterized database access. Escape user-generated content on output; do not trust client validation.
- Minimize precise location and identity data. Request location only when needed, avoid exposing exact coordinates to other users, restrict access, set retention limits, and support deletion where required.
- Never store raw payment card data. Verify signed provider webhooks, use idempotency for payment operations, and treat provider callbacks as untrusted until validated.
- Redact tokens, passwords, OTPs, personal data, location, message bodies, and payment details from logs and monitoring. Use request IDs for safe troubleshooting.
- Establish dependency updates, vulnerability reporting, backups with restore tests, incident response, and security testing before production.

## Reliability and performance

- Keep simple API operations synchronous. Use durable, idempotent, bounded jobs for moderation, notifications, webhooks, and check-in timers; surface terminal failures and make timers restart-safe.
- Add caching only for measured hot paths, with explicit expiry and invalidation. Do not cache sensitive responses in shared caches.
- Apply timeouts and bounded retries to provider calls. Distinguish pending, failed, and confirmed states for external operations.
- Add health checks, structured logs, error monitoring, and basic latency/error dashboards before launch. Set resource and request limits to reduce accidental overload and abuse.

## Delivery sequence

1. **Decide and gate:** confirm legal/provider scope, data retention, threat model, deployment region, and operational staffing.
2. **Foundation:** scaffold client/API, Go worker, CI, configuration/secrets, migrations, logging, and test environments.
3. **Trust and discovery:** implement email/Google auth, 21+ age review, gender check, profile/media moderation, GPS/approximate discovery, and preferences.
4. **Connections and safety:** implement connection limits, requester-first messaging, women-only live, accepted calls, block/report, emergency contact, booking check-ins, and admin operations.
5. **Controlled money flows:** implement call credits and provider-held meetup funds only after written legal/provider approval, manual settlement and dispute operations.
6. **Controlled pilot:** exercise backup restore, safety escalation, accessibility, contract compatibility, and incident response with a small approved cohort.

## Decisions to record as ADRs

Write a short Architecture Decision Record when a choice has lasting cross-team impact—for example, session and CSRF strategy, location precision/retention, selected payment or verification provider, deployment/data region, or moving work to asynchronous processing. Keep the record focused on context, decision, alternatives, and consequences.
