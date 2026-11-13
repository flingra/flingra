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

## Proposed page map

This is a product-scope starting point, not a list of existing routes. Build the first-release pages marked **Core** before adding optional integrations. Route names are illustrative; confirm final labels and flows with product and safety stakeholders.

### Public and account access

| Page | Example route | Scope | Purpose |
| --- | --- | --- | --- |
| Welcome / landing | `/` | Core | Explain the service, who it is for, and link to sign in or join. |
| Sign up | `/signup` | Core | Create an account with clear terms/privacy links and age eligibility confirmation. |
| Sign in | `/login` | Core | Authenticate and provide non-revealing error feedback. |
| Forgot / reset password | `/forgot-password`, `/reset-password` | Core | Recover account without revealing whether an email or phone is registered. |
| Verify contact | `/verify` | Core if verification is required for launch | Complete email or phone verification with resend limits and expiry feedback. |
| Terms and privacy | `/terms`, `/privacy` | Core | Present current policies before account creation and make them accessible later. |

### Signed-in member experience

| Page | Example route | Scope | Purpose |
| --- | --- | --- | --- |
| Onboarding | `/onboarding` | Core | Collect only required profile details, explain visibility, and allow users to skip optional data. |
| Discovery | `/discover` | Core | Browse eligible profiles using privacy-conscious location behavior; explain and handle denied location permission. |
| Member profile | `/members/:id` | Core | Show only fields intended for discovery and provide prominent block/report actions. |
| Edit profile | `/settings/profile` | Core | Review, update, and remove profile details and photos. |
| Safety and help | `/safety`, `/help` | Core | Explain safe use, reporting, blocking, and how to get support. |
| Report member | `/members/:id/report` | Core | Submit a report with clear categories, optional details, and confirmation without exposing the report to the reported member. |
| Account settings | `/settings` | Core | Manage account preferences and sign out. |
| Privacy and account deletion | `/settings/privacy` | Core | Explain data controls and provide a clear account deletion request flow with confirmation. |

### Add only when the feature is approved

| Page | Example route | Scope / prerequisite |
| --- | --- | --- |
| Inbox and conversation | `/inbox`, `/inbox/:conversationId` | Later: messaging must have blocking, reporting, abuse controls, and safe notification previews. |
| Verification | `/settings/verification` | Later: only after provider, evidence retention, review, and appeal policies are defined. |
| Payment / transaction history | `/payments`, `/payments/:id` | Later: only with an approved payment use case, provider integration, and dispute/refund support. Never collect card details in the client. |
| Notifications | `/settings/notifications` | Later: users need control over channels and sensitive-content previews. |
| Moderation console | Separate staff-only application or restricted route | Required before user-generated features scale; must use staff authorization, audit actions, and avoid broad access to sensitive data. |

### Navigation and shared states

- Public navigation should offer clear sign-in and join actions. Signed-in navigation should prioritize discovery, with settings and safety/help always reachable.
- Never rely on hiding a link as authorization; protect routes for usability and enforce permissions in the API.
- Every data-backed page needs loading, empty, error/retry, and expired-session states. Forms need validation, submission feedback, and recovery from network failure.
- Support direct links and browser back/forward navigation. Redirect signed-out users to sign-in without putting sensitive data in the return URL.
- Keep report/block confirmations and other safety-critical actions clear, private, keyboard-accessible, and usable on small screens.

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
