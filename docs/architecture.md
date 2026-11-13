# Flingra system blueprint

## Purpose and status

Flingra is a proposed Nigeria-first platform for consenting adults to discover connections, communicate, and plan meetups. Safety, privacy, and trust are foundational product requirements.

This repository is currently a scaffold. This blueprint captures a practical direction for implementation; it is not evidence that features, controls, providers, or compliance obligations are already in place. Validate applicable Nigerian and other launch-market laws, payment rules, and data-protection obligations with qualified counsel before launch.

## Product principles

1. **Adults and consent first.** Design for adults, clear consent, user control, and prompt safety response. Define an age-assurance and escalation approach before enabling discovery or messaging.
2. **Safety is a core workflow.** Users need accessible block, report, and support actions. Moderation needs restricted access, review records, and a documented escalation process.
3. **Privacy by default.** Collect the minimum data needed, explain its use, limit access and retention, and provide appropriate account/data deletion paths.
4. **Trust without overclaiming.** Verification signals must explain what was and was not checked; verification is not a guarantee of identity, safety, or conduct.
5. **Ship a narrow, reliable first release.** Defer costly integrations and real-time features until product value, safety readiness, and operational ownership are established.

## One shared member experience

Flingra is planned as one application for all eligible adults, not separate apps for men, women, lesbian, or gay users. Members should configure who they want to discover separately from who may discover them. Identity is not a proxy for those preferences, and sensitive identity details remain private unless a member chooses to display them.

Discovery must be filtered server-side: a profile is eligible to appear only when it meets the viewer's discovery preferences and the profile owner's visibility preferences, in addition to account eligibility and safety rules. For example, a man choosing to discover women should see eligible women whose visibility preferences include men; a woman choosing to discover women should see eligible women whose visibility preferences include women. These examples describe preference compatibility, not assumptions about a member's identity or a separate product experience.

The exact identity choices, preference options, and matching semantics remain product/privacy decisions to confirm before implementation. Keep the model flexible enough for members to select multiple audiences and change preferences without creating separate apps or disclosing private identity fields.

## Proposed first release

Define launch scope with product and safety stakeholders. A reasonable first increment is:

- Account creation, sign-in, account recovery, and a basic profile.
- A limited discovery experience with privacy-conscious location handling.
- Blocking and reporting, moderation review tools, and clear safety guidance.
- Operational logging/monitoring, support workflow, and account deletion process.

Messaging, identity verification, payments, push notifications, and live audio/video add significant safety, fraud, privacy, and operational responsibilities. Ship each only after its use case, abuse handling, provider contract, and support ownership are ready. Avoid collecting sensitive verification or payment data that a provider can safely retain instead.

## High-level architecture

```text
Browser
  └── React + TypeScript web client
        └── HTTPS API
              └── Go modular monolith (HTTP API)
                    ├── MySQL: durable application data
                    ├── Optional Redis: cache, rate limits, or queue broker
                    ├── Optional worker: bounded asynchronous jobs
                    └── Provider adapters: payment, SMS, maps, storage, etc.
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

Redis, a job queue, WebSockets, LiveKit, Google Maps, payment providers, Termii, Firebase Cloud Messaging, and S3-compatible storage are optional integrations, not baseline requirements. Choose providers after confirming regional availability, privacy and contractual terms, cost, reliability, and a tested fallback/failure path.

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

- Start with synchronous API operations for simple flows. Move slow or retryable tasks to a job queue only when needed; make jobs idempotent and bounded, with observable failures.
- Add caching only for measured hot paths, with explicit expiry and invalidation. Do not cache sensitive responses in shared caches.
- Apply timeouts and bounded retries to provider calls. Distinguish pending, failed, and confirmed states for external operations.
- Add health checks, structured logs, error monitoring, and basic latency/error dashboards before launch. Set resource and request limits to reduce accidental overload and abuse.

## Delivery sequence

1. **Decide:** confirm launch scope, adult-safety approach, data inventory/retention, threat model, deployment region, and provider/legal constraints.
2. **Foundation:** scaffold client and API, CI checks, configuration/secrets, database migrations, logging, and test environments.
3. **Safety-ready core:** build authentication, profile, limited discovery, block/report, moderation access controls, and account deletion; test authorization and abuse limits.
4. **Operate safely:** deploy to a controlled environment, exercise backup restore and incident procedures, test accessibility and critical user flows, and resolve security findings.
5. **Expand deliberately:** add messaging, verification, payments, notifications, maps, or real-time calls individually with product justification, threat review, provider failure handling, and monitoring.

## Decisions to record as ADRs

Write a short Architecture Decision Record when a choice has lasting cross-team impact—for example, session and CSRF strategy, location precision/retention, selected payment or verification provider, deployment/data region, or moving work to asynchronous processing. Keep the record focused on context, decision, alternatives, and consequences.
