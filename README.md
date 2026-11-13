# Flingra

Flingra is a proposed Nigeria-first, safety-focused platform for consenting adults to discover connections, communicate, and plan meetups. Trust, privacy, and user safety are core product requirements, not later add-ons.

This repository is currently a scaffold. The technology choices below are a recommended starting point, not implemented or finalized dependencies.

## Documentation

- [System blueprint](docs/architecture.md) — product boundaries, architecture, delivery phases, and shared security principles.
- [Frontend guide](frontend/README.md) — client structure, state, forms, accessibility, and frontend testing.
- [Backend guide](backend/README.md) — API, data, authentication, integrations, and backend testing.
- [Documentation index](docs/README.md) — how project documentation is organized.

## Proposed technology baseline

| Area | Starting recommendation |
| --- | --- |
| Web client | React, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router |
| Client data and forms | TanStack Query, React Hook Form, Zod; add Zustand only for genuinely shared client-only state |
| API | Go, `net/http`, OpenAPI |
| Data | MySQL 8.4 LTS, Go SQL driver, versioned SQL migrations |
| Runtime services | Durable worker for moderation, notifications, and booking check-ins; Redis only if needed |
| Testing | Vitest and Playwright; Go's `testing` package |
| Delivery | Docker, GitHub Actions, Sentry |

Integrations such as payments, SMS, push notifications, maps, object storage, and real-time audio/video should be selected and enabled only for a defined product requirement. Keep provider credentials server-side and verify regional availability, legal requirements, costs, and operational support before committing to a vendor.

## Repository layout

```text
.
├── backend/   # API and domain services
├── docs/      # Product and system documentation
├── frontend/  # Web client
└── README.md  # Project entry point
```

## Current status

Scaffold only: there is no runnable application, API, database schema, deployment pipeline, or completed security review yet. Use the guides to make implementation decisions explicit as the project grows.

## Contribution basics

- Keep changes scoped to the relevant application or documentation.
- Prefer small, reviewable changes and conventional commit messages.
- Update the relevant guide when behavior, architecture, or operational requirements change.
- Include tests and clear verification steps with pull requests.
