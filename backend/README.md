# Backend

The backend API is being built with Python and FastAPI, using MySQL as described in
[`frontend/architecture.md`](../frontend/architecture.md). It is designed to
implement the contract in [`frontend/docs/backend-handoff.md`](../frontend/docs/backend-handoff.md).

## Local setup

From this directory, install the package and test dependencies:

```sh
python -m pip install -e ".[test]"
```

Set `FLINGRA_DATABASE_URL` to a SQLAlchemy MySQL URL before starting the API.
For example, use the local development database URL supplied by your environment;
do not commit credentials. Optional settings include:

- `FLINGRA_ALLOWED_ORIGINS` — JSON list of trusted frontend origins.
- `FLINGRA_SESSION_COOKIE_SECURE` — keep enabled outside local HTTP development.
- `FLINGRA_SESSION_TTL_HOURS` — session lifetime.
- `FLINGRA_SMTP_HOST`, `FLINGRA_SMTP_PORT`, `FLINGRA_SMTP_USERNAME`,
  `FLINGRA_SMTP_PASSWORD`, and `FLINGRA_SMTP_FROM_ADDRESS` — email delivery.

Run the API with:

```sh
python -m uvicorn app.main:app --reload
```

`GET /health/live` checks that the process is running. `GET /health/ready`
checks that the database is configured and reachable. Database migrations must be
applied before feature endpoints are enabled.

## Current scope

The initial Python service foundation includes configuration, a database
readiness check, the frontend-compatible error envelope, and typed request and
profile schemas. Authentication, durable profile storage, and verification
endpoints are the next implementation slice; health status does not imply those
features are available yet.
