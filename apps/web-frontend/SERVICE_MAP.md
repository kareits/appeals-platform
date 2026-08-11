# SERVICE_MAP — web-frontend

Structured map of the web frontend. Kept current as behavior changes (Definition of Done, root
`CLAUDE.md`).

## Responsibility

The operator-facing single-page application (React + TypeScript). It renders login, the appeal
list/search UI, the manual appeal-registration form, and the appeal card (with comments and the card
commands), and talks exclusively to the BFF gateway over the same-origin `/api/v1` surface. It holds
no business logic and no direct access to Flowable, databases, or the filesystem (architectural
prohibition, root `CLAUDE.md`).

## Owned data

None. The only client-side state is the current session (access token and resolved claims), held in
`sessionStorage` for the tab session.

## Consumed API (BFF gateway)

| Method | Path                                    | Used for                                            |
| ------ | --------------------------------------- | --------------------------------------------------- |
| POST   | `/api/v1/auth/login`                    | Dev/local login → access token and claims.          |
| GET    | `/api/v1/tickets`                       | Appeal search/list with filters and pagination.     |
| POST   | `/api/v1/tickets`                       | Manual appeal registration (`ticket:create`).       |
| GET    | `/api/v1/reference-data`                | Reference-code selects and card labels.             |
| GET    | `/api/v1/tickets/{ticketId}/workspace`  | Appeal card + comments aggregation (`ticket:read`). |
| PATCH  | `/api/v1/tickets/{ticketId}`            | Edit card details (`ticket:update`).                |
| POST   | `/api/v1/tickets/{ticketId}/classify`   | Re-classify an appeal (`ticket:classify`).          |
| POST   | `/api/v1/tickets/{ticketId}/decision`   | Record a decision (`ticket:decide`).                |
| POST   | `/api/v1/tickets/{ticketId}/close`      | Close an appeal (`ticket:close`).                   |
| POST   | `/api/v1/tickets/{ticketId}/legal-hold` | Set/clear the legal hold (`ticket:legal_hold`).     |
| POST   | `/api/v1/tickets/{ticketId}/comments`   | Add a comment (`ticket:comment`).                   |

Transport types are a hand-maintained projection of `contracts/openapi/bff-service.v1.yaml`
(`src/api/types.ts`); update them when the BFF contract changes.

## Appeal card (01E-4)

- The card page (`src/features/tickets/TicketCardPage.tsx`, route `/tickets/:ticketId`) reads the
  aggregated workspace and renders the regulatory detail read-only, the applicants, the comments, and
  the command forms. The workspace `ticket` and `comments` section payloads (contract-opaque
  `unknown`) are narrowed with the same runtime decoders used on direct responses; a card decode
  failure fails closed, an unavailable/invalid comments section degrades.
- Command forms (`src/features/tickets/CardCommands.tsx`) are each rendered only when the caller holds
  the matching permission claim, so a first-line read-only user (`ticket:read` only) sees the card and
  comments with **no** editing controls (the gateway and Ticket Service enforce the same claims;
  UI gating is convenience, not the security boundary). Every command carries the card `version` as
  `expectedVersion` for optimistic locking; the forms remount on the new version after a successful
  command so their inputs reset to the refreshed card. Client-side validation
  (`src/features/tickets/cardCommandValues.ts`) mirrors the regulatory rules (a decision needs a code
  and text; a closure needs a reason and either a response date or a recorded reason for its absence).
- Dictionary codes on the card (status, stage, product, decision, closure reason, …) are shown with
  their localized business labels from the reference-data endpoint, falling back to the raw code.

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
safe rendering, the card view with first-line read-only gating and the command value builders, the
end-to-end registration→decision→close flow (via a stateful URL-routed `fetch` stub), and
frontend-to-BFF contract parity. `npm audit` runs in CI (fail on high/critical).

## Migrations

None (the frontend owns no database).

## Known limitations

- Status changes are placeholder in EP-1 (no Flowable): the card renders `currentStatusCode`/
  `currentStageCode` but the app never sets them; the process/mail/documents workspace sections are
  `not_implemented` placeholders until later phases.
- Dev/local login only (docs/06); corporate OIDC replaces it later (TASK_06).
- Minimal styling; the consistent visual design and accessibility pass is 01E-5.
