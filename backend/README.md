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
- `FLINGRA_ADMIN_ALLOWED_ORIGINS` — optional narrower JSON list accepted by
  admin login and admin CSRF checks; include those origins in
  `FLINGRA_ALLOWED_ORIGINS` as well when the admin UI is cross-origin.
- `FLINGRA_SESSION_COOKIE_SECURE` — keep enabled outside local HTTP development.
- `FLINGRA_SESSION_TTL_HOURS` — session lifetime.
- `FLINGRA_RATE_LIMIT_REDIS_URL` — Redis URL used by shared auth-abuse limits.
- `FLINGRA_RATE_LIMITING_ENABLED` — leave enabled outside isolated tests.
- `FLINGRA_MAX_REQUEST_BYTES` — maximum API request body (defaults to 1 MiB).
- `FLINGRA_GOOGLE_CLIENT_ID` — Google OAuth Web client ID used to verify
  Google Identity Services ID tokens. Add the same client ID to the authorized
  JavaScript origins in Google Cloud Console.
- `FLINGRA_BREVO_API_KEY` — secret API key for Brevo transactional email.
- `FLINGRA_BREVO_SENDER_EMAIL` — a verified sender address in Brevo.
- `FLINGRA_BREVO_SENDER_NAME` — optional sender display name.
- `FLINGRA_FRONTEND_URL` — frontend base URL used to construct password-reset links.
- `FLINGRA_TERMS_VERSION` and `FLINGRA_PRIVACY_VERSION` — accepted document versions.
- `FLINGRA_CLOUDINARY_CLOUD_NAME`, `FLINGRA_CLOUDINARY_API_KEY`, and
  `FLINGRA_CLOUDINARY_API_SECRET` — Cloudinary credentials. Keep the API secret
  private and configure all three before enabling media uploads.
- `FLINGRA_MEDIA_UPLOAD_MAX_BYTES` — maximum size of each uploaded image
  (default 10 MiB).

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
create and alter application tables, add indexes/foreign keys, and create
triggers for the append-only audit log. If your
database provider does not grant these privileges to the application user, set
`FLINGRA_MIGRATION_DATABASE_URL` to a separate migration/admin connection or
have the database administrator apply the SQL migrations. Do not grant the
runtime account broad DDL privileges just to make the application start.

The migration command applies the existing account/session migrations, the
forward migration aligning account identifiers, genders, and profiles with the
frontend contract, the migration removing facial-verification data, and the
media metadata, admin/audit, and Google-account-link migrations. It records applied migration
filenames in `schema_migrations`.
For a database containing the legacy tables but no migration history, it marks
the four existing migrations as the baseline, then applies the remaining
migrations in order.
Review and back up a non-disposable database before applying schema changes.

Run the API with:

```sh
python -m uvicorn app.main:app --reload
```

`GET /health/live` checks that the process is running. `GET /health/ready`
checks that the database is configured and reachable. Database migrations must be
applied before feature endpoints are enabled. On startup, the Uvicorn terminal
logs whether the database connection check succeeded or failed; the API still
starts if the database is unavailable so the process liveness endpoint remains usable.

## Current scope

Implemented endpoints:

- `POST /auth/signup`, `/auth/login`, `/auth/verify-contact`, `/auth/resend-code`
- `GET /auth/oauth/google/config`, `POST /auth/oauth/google`
- `POST /auth/password/forgot`, `/auth/password/reset`, `/auth/logout`
- `GET /auth/session`, `POST /auth/onboarding/complete`
- `GET /profiles/me`, `PATCH /profiles/me`
- `POST /media/photos`, `POST /media/documents`, `GET /media/{media_id}`
- `POST /admin/auth/login`, `GET /admin/auth/session`, `POST /admin/auth/logout`
- `GET /admin/reviews`, `GET /admin/reviews/{review_id}`
- `GET /admin/reviews/{review_id}/document`
- `POST /admin/reviews/{review_id}/decision`
- `GET /admin/users/{account_id}/audit`
- `GET /admin/admins`, `PATCH /admin/admins/{admin_id}` (super admin only)

Admin accounts are separate from user accounts and cannot self-register. After
applying migrations, provision staff accounts from the backend environment
with `python -m app.create_admin`; the first account is a super admin, and
subsequent accounts default to reviewers. Use
`--role reviewer|safety_admin|auditor|super_admin` to select a role explicitly.
For an existing installation, migrated admins receive the reviewer role; create
a super admin with `python -m app.create_admin --role super_admin`. The command
prompts for the email and a confirmed password (minimum 14 characters) without
placing the password in shell history or environment variables. Admin sessions
use separate
`HttpOnly`, `SameSite=Strict`, `/admin`-scoped cookies with an 8-hour maximum
life, and require CSRF tokens and an allowlisted `Origin` when origins are
configured. Set `FLINGRA_ADMIN_ALLOWED_ORIGINS` to the separate admin UI
origin(s) in production; otherwise admin requests use the general
`FLINGRA_ALLOWED_ORIGINS` allowlist. Admin login is rate-limited through Redis and locks the account after repeated
failures. Do not expose the admin API without TLS, configured
trusted origins, and available Redis rate-limit storage.

Admin authorization is role-based and enforced on every protected endpoint:

| Role | Permissions |
| --- | --- |
| `super_admin` | All admin operations; manage staff roles and disable/enable accounts |
| `reviewer` | View profile/document review queues and details; view documents and decide reviews |
| `safety_admin` | Read user-scoped audit history; reserved for authorized safety-case workflows |
| `auditor` | Read user-scoped audit history only |

Only a super admin can list or update admin accounts. Role/disable changes are
CSRF-protected and audited; disabling an account revokes its active sessions.
Admins cannot change their own role or status, and the last active super admin
cannot be demoted or disabled. Exact-location access is not implemented by any
current endpoint; if added, it should be restricted to an audited safety-case
workflow rather than granted generally to all admin roles.

Review IDs are prefixed (`profile-<id>` or `document-<id>`). The review queue
supports `type=profile|identity-document|all`, bounded `limit`, and `offset`.
Decision requests require `{"decision":"approved|rejected","reason":"..."}`;
the profile/document state change and audit record commit together. Document
access requires an active admin session and returns a short-lived private
storage URL. Keep the bucket private.

Every request receives an `X-Request-ID`. The append-only
`platform_audit_events` table records successful and failed authentication,
verification and password-reset actions, profile changes/reads, media uploads
and access attempts, and admin review queue/detail/document/decision actions.
Events include the actor, affected account where applicable, outcome,
timestamp, request ID, and narrowly scoped metadata; credentials, tokens,
document contents, and full request bodies are never recorded. Admin audit
access is user-scoped and paginated in chronological order:
`GET /admin/users/{account_id}/audit?limit=50&offset=0`, optionally filtered by
`eventType` and `outcome`. Viewing the queue, a review, a document, or that
user's history is itself audited against the affected account. Unknown-account
authentication attempts are recorded without storing the submitted identifier.
Audit events are protected against update/delete by database triggers; also
grant the runtime database role only the `SELECT` and `INSERT` privileges it
needs on `platform_audit_events`. Define and review a legally appropriate
retention/backup policy before production; append-only does not replace
independent, access-controlled backups or operational monitoring.
New endpoints and background jobs must write an audit event in the same
database transaction as a state change, and record protected-data reads before
returning the data. Use stable event names and safe metadata only; do not log
request bodies, OTPs, passwords, session/CSRF tokens, raw identifiers, or
identity-document contents.

Current event names include `auth.signup`, `auth.login`,
`auth.contact_verification`, `auth.verification_code_resend`,
`auth.password_reset_requested`, `auth.password_reset_completed`,
`auth.logout`, `auth.csrf.denied`, `profile.own_viewed`, `profile.updated`,
`profile.onboarding_completed`, `media.profile_photo.uploaded`,
`media.identity_document.uploaded`, `media.access`, `admin.login`,
`admin.login_origin.denied`, `admin.account.created`, `admin.logout`,
`admin.csrf.denied`, `admin.review.queue_viewed`,
`admin.review.queue_item_viewed`, `admin.review.details_viewed`,
`admin.review.document_viewed`, `admin.review.decided`, and
`admin.audit.user_history_viewed`, `admin.account.list_viewed`,
`admin.account.updated`, `admin.account.update_denied`, and
`admin.authorization.denied`. Outcomes are
`success`, `failure`, or `denied`. User audit history is chronological (oldest first), with stable
event IDs and request IDs for correlation.

Session cookies are HttpOnly; mutating authenticated endpoints require the
`X-CSRF-Token` value paired with the `flingra_csrf` cookie. When
`FLINGRA_ALLOWED_ORIGINS` is configured, these requests must also carry a
matching `Origin` header. The API applies request-size limits and security
headers. Email verification
and password resets use Brevo's transactional email API and require a configured
API key and verified sender address. The API key is loaded as a secret and is
never included in logs or API error responses. Phone-based signup is
currently unavailable until an SMS provider is configured. Facial/selfie
verification is not used. Completed profiles enter pending moderation for manual admin review. The
backend now supports basic profile/document approval and rejection, but does
not yet implement report queues, blocking controls, admin MFA, password
rotation/recovery, or an admin frontend. The frontend
still uses its mock API and will need an API-client integration before it
calls these routes.

Media endpoints require verified, authenticated accounts and CSRF tokens.
Uploaded JPEG/PNG/WebP images are decoded and re-encoded as JPEG to remove
metadata, with input-size and pixel-count limits. Files are uploaded to
Cloudinary as authenticated assets. MySQL stores the Cloudinary public ID in
`media_objects.object_key`; users receive the backend `/media/{media_id}` URL,
not a provider URL. After authorization, the backend redirects to a
short-lived Cloudinary download URL. Configure the Cloudinary credentials and
apply the `000007` media migration before using these endpoints. Do not upload
sensitive production documents until retention and deletion procedures are in
place.

Switching from R2 does not copy existing files to Cloudinary. Migrate any
existing objects before changing providers, or their stored identifiers will no
longer resolve. Uploaded Cloudinary files are not yet deleted when an account is
removed; implement and test that cleanup before accepting production media.
