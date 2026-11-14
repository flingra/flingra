# Backend
 
The backend API is being built with Python and FastAPI, using MySQL as described in
[`frontend/architecture.md`](../frontend/architecture.md). It is designed to
implement the contract in [`frontend/docs/backend-handoff.md`](../frontend/docs/backend-handoff.md).

## Local setup

From this directory, install the package and test dependencies:

```sh
python -m pip install -e ".[test]"
```

Configure MySQL either with `FLINGRA_DATABASE_URL` (SQLAlchemy URL) or with
these separate fields in `backend/.env`:

- `FLINGRA_DB_HOST`, `FLINGRA_DB_PORT`, `FLINGRA_DB_NAME`
- `FLINGRA_DB_USER`, `FLINGRA_DB_PASSWORD`
- `FLINGRA_DB_SSL_MODE` (use `REQUIRED` for encrypted Aiven connections)
- `FLINGRA_DB_SSL_CA` (optional CA certificate path; when provided, the
  certificate and server identity are verified)

The separate fields avoid URL-encoding issues in passwords. Keep `.env`
uncommitted and do not share database credentials. For production, prefer
`VERIFY_IDENTITY` with the CA certificate downloaded from your database
provider. `REQUIRED` without a CA encrypts traffic but does not authenticate
the server certificate.

Optional settings include:

- `FLINGRA_MIGRATION_DATABASE_URL` — optional database URL for the migration
  runner only. It can use a migration role with DDL permissions while
  runtime `FLINGRA_DATABASE_URL` or `FLINGRA_DB_*` settings remain more
  restricted.
- `FLINGRA_ALLOWED_ORIGINS` — JSON list of trusted frontend origins.
- `FLINGRA_SESSION_COOKIE_SECURE` — keep enabled outside local HTTP development.
- `FLINGRA_SESSION_TTL_HOURS` — session lifetime.
- `FLINGRA_RATE_LIMIT_REDIS_URL` — Redis URL used by shared auth-abuse limits.
- `FLINGRA_RATE_LIMITING_ENABLED` — leave enabled outside isolated tests.
- `FLINGRA_MAX_REQUEST_BYTES` — maximum API request body (defaults to 1 MiB).
- `FLINGRA_BREVO_API_KEY` — secret API key for Brevo transactional email.
- `FLINGRA_BREVO_SENDER_EMAIL` — a verified sender address in Brevo.
- `FLINGRA_BREVO_SENDER_NAME` — optional sender display name.
- `FLINGRA_FRONTEND_URL` — frontend base URL used to construct password-reset links.
- `FLINGRA_TERMS_VERSION` and `FLINGRA_PRIVACY_VERSION` — accepted document versions.

Configure Redis before exposing auth routes, for example with
`FLINGRA_RATE_LIMIT_REDIS_URL=redis://localhost:6379/0`. Sensitive auth routes
fail closed with `503` if Redis is missing or unavailable; `/health/ready`
also reports the service as unavailable. Do not disable rate limiting in a
deployed environment. When running behind a reverse proxy, configure Uvicorn's
`--proxy-headers` and `--forwarded-allow-ips` only for the actual proxy addresses
so clients cannot spoof the IP used by rate limits.

Apply the SQL migrations once after configuring the database:

```sh
python -m app.migrate
```

The migration account needs permission to create the migration-history table,
create and alter application tables, and add indexes/foreign keys. If your
database provider does not grant these privileges to the application user, set
`FLINGRA_MIGRATION_DATABASE_URL` to a separate migration/admin connection or
have the database administrator apply the SQL migrations. Do not grant the
runtime account broad DDL privileges just to make the application start.

The migration command applies the existing account/session migrations and the
forward migration aligning account identifiers, genders, and profiles with the
frontend contract. It records applied migration filenames in `schema_migrations`.
For a database containing the legacy tables but no migration history, it marks
the four existing migrations as the baseline, then applies the new migration.
Review and back up a non-disposable database before applying schema changes.

Run the API with:

```sh
python -m uvicorn app.main:app --reload
```

`GET /health/live` checks that the process is running. `GET /health/ready`
checks that the database is configured and reachable. Database migrations must be
applied before feature endpoints are enabled. On startup, the Uvicorn terminal
logs whether the database connection check succeeded or failed; the API still
starts if the database is unavailable so the liveness endpoint remains usable.

## Current scope

Implemented endpoints:

- `POST /auth/signup`, `/auth/login`, `/auth/verify-contact`, `/auth/resend-code`
- `POST /auth/password/forgot`, `/auth/password/reset`, `/auth/logout`
- `GET /auth/session`, `POST /auth/onboarding/complete`
- `GET /profiles/me`, `PATCH /profiles/me`

Session cookies are HttpOnly; mutating authenticated endpoints require the
`X-CSRF-Token` value paired with the `flingra_csrf` cookie. When
`FLINGRA_ALLOWED_ORIGINS` is configured, these requests must also carry a
matching `Origin` header. The API applies request-size limits and security
headers. Email verification
and password resets use Brevo's transactional email API and require a configured
API key and verified sender address. The API key is loaded as a secret and is
never included in logs or API error responses. Phone-based signup is
currently unavailable until an SMS provider is configured. Selfie verification
cannot be marked verified by the client, so onboarding completion remains
blocked until a real verification provider is connected. The frontend still
uses its mock API and will need an API-client integration before it calls these
routes.
