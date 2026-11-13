# Backend

The backend API and domain services will live in this directory. The repository is currently a scaffold; this guide describes the agreed Go direction and a practical implementation baseline, not an implemented service.

See the [system blueprint](../docs/architecture.md) for whole-system design and shared security requirements, and the [frontend specification](../frontend/README.md) for page flows and client/API expectations.

## Proposed baseline

- **Language/runtime:** Go; use the current stable Go release supported by the deployment platform and pin the toolchain in CI.
- **HTTP:** Start with Go's standard `net/http` package and its `ServeMux`. Add a small router/library only for a demonstrated need; avoid choosing a large framework by default.
- **API contract:** OpenAPI as the documented contract. Keep request and response types explicit and validate inputs at the HTTP boundary.
- **Database:** MySQL 8.4 LTS, `database/sql`, and a maintained MySQL driver. Use parameterized queries. Consider `sqlc` to generate type-safe query code from SQL; do not introduce it until the team agrees it fits the workflow.
- **Migrations:** Versioned SQL migration files and a migration tool selected during bootstrap. Migrations run as a controlled deployment step, not implicitly on every API startup.
- **Testing:** Go's standard `testing` package, `httptest`, and a real disposable MySQL test database for persistence and migration coverage.
- **Operations:** Docker, GitHub Actions, structured redacted logs, health/readiness endpoints, and Sentry or an equivalent error-monitoring integration.

Keep the implementation a modular monolith: one deployable API with clear feature/domain boundaries. Do not split into microservices until a measurable scaling or team-ownership need justifies the added operational cost.

Redis, background jobs, WebSockets, and external services are optional. Add them only for a defined use case, with explicit timeout, retry, idempotency, and failure behavior. Keep the initial service synchronous where that is sufficient.

## Suggested package layout

Prefer a layout organized around the application rather than a large collection of generic layers:

```text
backend/
  cmd/
    api/                 # API process entry point
  internal/
    auth/                # Authentication and session rules
    profile/             # Profile and discovery domain
    safety/              # Blocking, reporting, moderation boundaries
    platform/
      config/            # Validated configuration
      database/          # DB setup and shared transaction helpers
      http/              # Middleware and transport helpers
  migrations/            # Versioned SQL schema changes
  api/                   # OpenAPI specification
  go.mod
```

This is a suggested shape, not a requirement to create empty packages now. Keep domain rules out of HTTP handlers and prevent feature packages from importing unrelated internals unnecessarily.

## HTTP API and data conventions

- Use a consistent API prefix/version, documented request/response schemas, and stable error codes. Publish or serve the OpenAPI contract from the API specification.
- Parse and validate every untrusted input at the boundary. Set request body, query, pagination, and upload limits.
- Enforce authentication and authorization on every protected operation in the backend. A hidden frontend button or route guard is not an access control.
- Return explicit response DTOs; do not expose database rows or internal structs directly. Mark public, owner-only, and staff-only fields intentionally.
- Use parameterized SQL with context-aware queries. Avoid building SQL from user-provided strings; allowlist any dynamic sort/filter identifiers.
- Use transactions for multi-step state changes. Handle unique constraints and concurrent requests explicitly.
- Store times consistently in UTC. Make schema changes reviewable, ordered, and safe for deployment; provide a tested rollback or forward-recovery plan.
- Apply bounded pagination to discovery, reports, and other collections. Set sane server and database timeouts.
- Keep server configuration typed and validated at startup. Fail clearly when required configuration is missing; do not silently fall back to insecure defaults.

## Authentication and sensitive data

- Hash passwords with Argon2id using a maintained Go implementation and documented parameters. Never store plaintext passwords or reversible password encryption.
- For browser sessions, prefer short-lived sessions with `Secure`, `HttpOnly`, appropriately `SameSite` cookies, refresh rotation/revocation, and CSRF defenses for cookie-authenticated state-changing requests.
- Rate-limit sign-in, OTP, recovery, and other abuse-prone endpoints. Use generic account-recovery responses to reduce account enumeration.
- Authorize every resource access against the authenticated user and resource relationship; test object-level authorization, not only route-level login checks.
- Collect the minimum personal data needed. Define retention/deletion behavior and restrict staff access. Treat location, identity evidence, reports, messages, and payment metadata as sensitive.
- Never store payment card data. Verify provider webhook signatures, enforce idempotency, and reconcile provider events before changing payment state.
- Redact passwords, cookies, tokens, OTPs, personal data, precise location, message/report contents, and payment details from logs and monitoring. Use request IDs for safe troubleshooting.
- Keep secrets out of source control and container images. Inject them from a managed secret store, separate environments, and rotate credentials.

## Integrations and reliability

Wrap payment, SMS/OTP, push, maps, file storage, and real-time providers behind narrow interfaces so domain code does not depend on vendor-specific request formats.

- Set explicit timeouts for outbound HTTP, database connections, and request handling. Propagate `context.Context` cancellation and deadlines.
- Retry only transient failures, with bounded attempts and backoff. Do not retry non-idempotent operations unless protected with idempotency keys.
- Represent external workflows such as payments and verification with explicit pending/confirmed/failed states. Do not report success until confirmed.
- If adding background workers, make jobs idempotent, bounded, observable, and safe to retry; surface terminal failures.
- Before production, define health/readiness checks, structured redacted logs, error monitoring, backups and restore tests, migration procedures, and incident escalation.
- Protect staff/moderation operations with least-privilege authorization and auditable actions.

## Testing

- Unit-test domain rules, validation, and authorization decisions with the standard `testing` package.
- Use `httptest` for HTTP handlers, middleware, error behavior, and request limits.
- Integration-test migrations, transaction behavior, and queries against a disposable MySQL instance where feasible.
- Test unauthenticated and forbidden access, cross-account resource access, rate limits, session/CSRF behavior, and webhook signature verification.
- Test timeouts and provider failures without calling real services in normal CI.
- Use synthetic fixtures only; never copy production personal data into local or CI environments.

## Local development

There is no Go module or backend application yet. When bootstrapping, document the supported Go toolchain and verified commands for dependency setup, local configuration, migrations, running the API, formatting, static analysis, and tests. Keep local secrets in an ignored environment file and commit only a placeholder `.env.example`.
