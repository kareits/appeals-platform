# SERVICE_MAP — web-frontend

Structured map of the web frontend. Kept current as behavior changes (Definition of Done, root
`CLAUDE.md`).

## Responsibility

The operator-facing single-page application (React + TypeScript). It renders login, the appeal
list/search UI, and the manual appeal-registration form, and talks exclusively to the BFF gateway
over the same-origin `/api/v1` surface. It holds no business logic and no direct access to Flowable,
databases, or the filesystem (architectural prohibition, root `CLAUDE.md`).

## Owned data

None. The only client-side state is the current session (access token and resolved claims), held in
`sessionStorage` for the tab session.

## Consumed API (BFF gateway)

| Method | Path                     | Used for                                          |
| ------ | ------------------------ | ------------------------------------------------- |
| POST   | `/api/v1/auth/login`     | Dev/local login → access token and claims.        |
| GET    | `/api/v1/tickets`        | Appeal search/list with filters and pagination.   |
| POST   | `/api/v1/tickets`        | Manual appeal registration (`ticket:create`).     |
| GET    | `/api/v1/reference-data` | Reference-code selects for the registration form. |

Transport types are a hand-maintained projection of `contracts/openapi/bff-service.v1.yaml`
(`src/api/types.ts`); update them when the BFF contract changes. Later subtasks consume more of the
gateway API (workspace, card commands).

## Auth and session

- Login stores the access token and claims in `sessionStorage` (`src/auth/session.ts`); a restored
  session is fully validated (fail closed) before it is trusted.
- The API client attaches the bearer token and an `X-Correlation-ID` to every request
  (`src/api/client.ts`); a `401` clears the session **and the shared query cache** and the route
  guard redirects to `/login` (`src/routing/RequireAuth.tsx`).
- Permission claims are available via the auth context (`hasPermission`) for future UI gating.

## Client-state isolation

Protected query keys are scoped by the authenticated subject (`useTicketSearch`), and logout/401
cancel in-flight protected queries (aborting their fetches) and clear the shared `QueryClient`
(`src/auth/AuthContext.tsx`). A later login in the same tab therefore cannot render or reuse the
previous user's cached data, and a request that completes after logout cannot populate the cache
(regression: `src/features/tickets/cacheIsolation.test.tsx`).

## Runtime validation and error handling

- No response is trusted via `as T`. Media types are matched **exactly** (parameters stripped, case
  and whitespace normalized): a 2xx body is read only under `application/json`, and an RFC 7807 error
  only under `application/problem+json`. Any near match (`application/jsonp`, `text/application/json`,
  `application/problem+jsonp`, or a plain `application/json` on the error path) fails closed as a
  `ProtocolError` (`src/api/errors.ts`); a bodyless error still surfaces its status. Bodies are then
  validated by a hand-written decoder (`src/api/decoders.ts`): required/nullable fields, element
  types, contracted UUID formats, real offset-aware ISO-8601 date-times (calendar/leap-year/range
  correct, not just regex-shaped), a positive token lifetime, supported roles (fail closed), and
  pagination bounds. A restored session is validated the same way — its subject as a UUID and its
  roles against the supported set; the diagnostic correlation id is accepted only under a bounded
  charset/length policy. All real gateway errors are `application/problem+json` (verified live,
  including gateway-side request-validation 422s), so the exact-media rule rejects only anomalous
  responses.
- The query's `AbortSignal` is threaded through the endpoint and client into `fetch`, so superseded
  searches, navigation, unmount, and logout cancel the request; a client-side timeout is distinct
  from a network failure and from a caller cancellation (which is silent).
- Each contracted gateway status (400/401/403/404/409/413/422/429/5xx), a timeout, a network
  failure, and an invalid response map to a distinct localized message (`src/api/errorMessages.ts`);
  a 429 shows a bounded `Retry-After` hint and a manual retry. The diagnostic correlation id is
  shown separately and never embedded in the user message.

## Localization

All user-facing copy lives in `src/i18n/locales/ru.json` and `kk.json` (react-i18next). Russian is
the default and fallback; a switcher toggles Russian/Kazakh (ADR-015: business/UI text is allowed in
Russian and Kazakh and is separated from technical code).

## Build and runtime

- Built with Vite to static assets (`dist/`). Node.js is a build/test-time tool only; the dev and
  preview servers bind to loopback.
- Runtime image: `caddy:2.8-alpine` serving the static bundle with a single-page-app routing
  fallback (`apps/web-frontend/Caddyfile`). No Node runs in production. The container runs as a
  dedicated non-root user (UID/GID 10001) on the unprivileged port 8080, with a read-only root
  filesystem (writable tmpfs only for `/tmp`, `/data`, `/config`), `no-new-privileges`, and all
  Linux capabilities dropped (CR-WEB-LOW-001).
- Every response (including the SPA deep-link fallback) carries a strict same-origin CSP
  (`object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`), `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Referrer-Policy`, and `Permissions-Policy`. The HTML shell is served
  `no-cache`; fingerprinted `/assets/*` are `immutable` (CR-WEB-MEDIUM-003).
- The platform edge reverse proxy routes `/api` and `/health` to the BFF and everything else to this
  SPA, so the app is same-origin with the gateway (no CORS); the SPA security headers pass through.

## External dependencies

- BFF service (HTTP, same origin) — the only backend the app calls.

## Failure behavior

- Missing/invalid session → redirect to `/login`; a `401` on any request clears the session and the
  query cache.
- Search failures map to distinct localized messages: `403` → a permission message; `429` → a
  Retry-After hint with manual retry; `400/404/409/413/422`, `5xx`, timeout, network, and invalid
  responses each get their own message; empty results → an explicit empty state.
- Gateway errors (RFC 7807) are surfaced as localized messages by HTTP status; downstream `detail`
  text is never rendered, and the correlation id is shown only as a separate diagnostic line.

## Testing

`npm test` (Vitest + Testing Library). Tests stub `fetch` (including headers, media type, invalid
JSON, and deferred/abortable responses) and exercise the real API client, decoders, auth context,
and TanStack Query: login success/invalid/malformed-response, malformed/missing session, the seven
roles and unknown-role fail-closed, list/empty/forbidden, filter mapping and pagination, all
contracted error statuses and Retry-After, timeout/network/invalid-shape, correlation diagnostics,
request cancellation on unmount, two-user cache isolation (including post-logout completion), XSS-
safe rendering, and frontend-to-BFF contract parity. `npm audit` runs in CI (fail on high/critical).

## Migrations

None (the frontend owns no database).

## Known limitations

- Appeal card/comments/decision/close are delivered in 01E-4; manual registration in 01E-3.
- Dev/local login only (docs/06); corporate OIDC replaces it later (TASK_06).
- Minimal styling; no design system in this milestone.
