# Flingra

Flingra is a Nigeria-first social connection and meetup platform for adults,
with location-aware discovery, messaging, verification, safety tools, wallet
payments, calls, and livestreams.

## Project structure

- `frontend/` — React, TypeScript, and Vite web client.
- `backend/` — FastAPI application, database migrations, and tests.
- `docs/` — product and integration documentation.

The frontend uses the backend API for its account and product flows. Payments,
media delivery, email/SMS, calls, and livestream media also require the
corresponding external provider credentials and production dashboard settings;
source code alone cannot verify those deployments.

## Current integrations

- Paystack handles wallet top-ups and bank payouts.
- LiveKit provides call and livestream media rooms.
- Cloudinary stores uploaded media.
- Brevo handles transactional email; Termii is required for SMS safety
  notifications.
- Referral codes are available, but referral bonus crediting is disabled.

See [backend/README.md](./backend/README.md) and the
[frontend integration guide](./frontend/docs/frontend-backend-integration-guide.md)
for setup requirements and provider configuration.
