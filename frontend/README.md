# Frontend

The web client will live in this directory. The repository is currently a scaffold; these are implementation conventions for the proposed React and TypeScript application.

See the [system blueprint](../docs/architecture.md) for shared product and security decisions.

## Proposed baseline

- React, TypeScript, and Vite.
- React Router for route-level navigation.
- Tailwind CSS and shadcn/ui for styling and accessible UI building blocks.
- TanStack Query for server state and API caching.
- React Hook Form and Zod for forms and client-side input feedback.
- Zustand only when state is shared across routes and does not belong in the URL, a form, or the server cache.
- Axios if its shared interceptors and request configuration are useful; keep API access behind a small typed client rather than calling it throughout components.

These are recommendations, not installed dependencies. Keep the initial client small and add libraries only to solve a current need.

## Suggested structure

Organize by product feature as the application grows, rather than creating many empty framework-specific layers:

```text
src/
  app/          # App setup, providers, and route configuration
  features/     # Feature pages, components, hooks, and schemas
  components/   # Small shared UI components
  lib/          # API client and cross-feature utilities
```

Keep feature-specific code inside its feature. Promote code to shared folders only when there is a real second use.

## Client behavior and security

- Treat the API as authoritative. Client validation improves usability; backend validation is mandatory.
- Do not put access tokens, refresh tokens, secrets, or sensitive personal data in `localStorage`, URLs, analytics, or console logs. Prefer secure, `HttpOnly`, `SameSite` cookies for browser sessions, with CSRF defenses appropriate to the deployment.
- Render user-generated content as text by default. Do not use unsafe HTML rendering for profile or message content.
- Ask for browser location only when needed, explain why, and support denial. Avoid persisting precise coordinates in client state longer than necessary.
- Show clear loading, empty, error, permission-denied, and retry states. Do not make failed API requests look successful.
- Make safety actions such as block and report easy to find, and avoid exposing sensitive profile details in notifications or previews.
- Follow accessible semantic HTML, keyboard navigation, visible focus, and sufficient contrast.

## Testing

- Vitest for unit and component tests; test user-visible behavior and important validation.
- Playwright for critical end-to-end flows, including sign-in/session expiry, reporting/blocking, and permission-denied states.
- Keep secrets and production personal data out of test fixtures, screenshots, and CI logs.

## Local development

There is no frontend app or package manifest yet. When bootstrapping, document the supported Node.js version and exact install, development, lint, type-check, and test commands here. Do not claim a command works until it exists and has been verified.
