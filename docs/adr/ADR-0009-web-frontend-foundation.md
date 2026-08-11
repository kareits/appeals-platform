# ADR-0009: Web-frontend foundation — SPA stack, gateway-only access, and same-origin edge routing

- **Status:** Accepted (the "minimal styling, no design system" scope is superseded by
  [ADR-0011](ADR-0011-frontend-design-system.md), TASK_01E-5; all other decisions here stand)
- **Related:** ADR-002 (approved stack: React + TypeScript); ADR-0007 (BFF gateway — the single
  frontend API); ADR-0008 (Ticket-service independent authorization); ADR-015 (language policy —
  Russian/Kazakh UI text in the localization layer); ADR-AUTH-OIDC (dev-auth → corporate OIDC,
  TASK_06); BFF_SERVICE spec; docs/05 (API/error/correlation conventions)

## Context

TASK_01E-2 introduces the operator web frontend — the first frontend subtask. Per the
context-loading guide, the EP-1 frontend subtasks change only the `apps/` frontend (the backend
services, including the BFF, are frozen after 01E-1), so this milestone must stand up the whole
frontend foundation while delivering the 01E-2 scope: dev-login and the appeal list with
search/filter. The approved stack is React + TypeScript (ADR-002). The BFF already exposes the full
gateway surface the EP-1 frontend needs (ADR-0007), and both the gateway and the Ticket Service
enforce authorization independently (ADR-0008), so the frontend is a pure presentation client.

## Decision

- **React + TypeScript SPA built with Vite (ADR-002).** The toolchain (TypeScript, Vite, ESLint,
  Vitest) runs on Node.js at **build/test time only**. The deployed artifact is static files; no
  Node process runs in production. This keeps the platform's runtime footprint unchanged — the
  frontend adds static assets, not a long-running Node service.
- **Gateway-only access.** The SPA talks exclusively to the BFF over the same-origin `/api/v1`
  surface; it never reaches IAM, the Ticket Service, Flowable, databases, or the filesystem directly
  (architectural prohibition). Transport types are a hand-maintained projection of
  `contracts/openapi/bff-service.v1.yaml`, not a shared domain model, so the contract stays the
  single source of truth and the frontend carries no business logic.
- **Same-origin edge routing (no CORS).** The platform edge reverse proxy routes `/api` and the BFF
  `/health` endpoints to the BFF and serves everything else from the `web_frontend` container (the
  compiled SPA with a client-side routing fallback). One origin means no CORS and no cross-site
  cookie/token complexity. The `web_frontend` runtime image is `caddy:2.8-alpine` serving static
  assets.
- **Session and auth handling forward-compatible with OIDC.** Login uses the temporary dev/local
  scheme via the gateway (docs/06); the access token and resolved claims are held in
  `sessionStorage` for the tab session. The API client attaches the bearer token and an
  `X-Correlation-ID` per request; a `401` clears the session and the route guard redirects to login.
  Permission claims are available to the UI (`hasPermission`) for gating. Nothing about the client
  depends on the token being an HS256 dev token, so the corporate OIDC transition (ADR-AUTH-OIDC)
  does not change the frontend.
- **Server state via TanStack Query; localization via react-i18next.** TanStack Query owns
  server-state (caching, loading/error, pagination) as the foundation for the card and mutations in
  01E-3/01E-4. All user-facing copy lives in `src/i18n/locales/{ru,kk}.json` (ADR-015); technical
  code hard-codes no Russian or Kazakh strings. Russian is the default and fallback; a switcher
  toggles Russian/Kazakh.
- **Its own quality gates in CI.** A dedicated `frontend` CI job runs ESLint, Prettier, `tsc`,
  Vitest, and the Vite build, mirroring the Python `make check` gates for the frontend.

## Alternatives considered

- **Server-rendered UI from a Python service (no SPA / no Node toolchain):** rejected — it
  contradicts the approved stack (ADR-002) and there is no React toolchain that does not run on
  Node; it would also duplicate presentation state the SPA needs for the later interactive card.
- **A separate frontend host/origin with CORS on the BFF:** rejected — same-origin edge routing is
  simpler and avoids CORS and cross-site token handling. The edge proxy already fronts the BFF.
- **Generate TypeScript types from the OpenAPI contract:** deferred — a hand-maintained projection
  of the small surface used here is sufficient and avoids adding a codegen step now; revisit as the
  consumed surface grows in 01E-3/01E-4.
- **Persist the token in `localStorage`:** rejected for now — `sessionStorage` limits the token's
  lifetime to the tab session for the temporary dev scheme; the durable story is corporate OIDC
  (TASK_06).
- **Redux / a global store for server data:** rejected — TanStack Query covers server-state; local
  UI state is small enough for component state, avoiding an extra abstraction.

## Security hardening (TASK_01E-2 review remediation)

The independent review (CODE_REVIEW_REPORT section 29) required the following decisions before the
slice is safe to commit; they refine, not reverse, the foundation above:

- **Subject-scoped client state.** Protected query keys include the authenticated subject, and
  logout/401 cancel in-flight protected queries and clear the shared `QueryClient`. The global cache
  must never cross the authentication ownership boundary (CR-WEB-HIGH-001).
- **Fail-closed runtime validation.** Responses and restored sessions are validated by hand-written
  decoders: exact media types (a 2xx only under `application/json`, an RFC 7807 error only under
  `application/problem+json`; every near match fails closed), required/nullable fields, element
  types, contracted UUID formats, real calendar-correct offset-aware date-times, a positive token
  lifetime, supported roles and a UUID subject (including on session restore), pagination bounds,
  and a bounded correlation id; a violation is a `ProtocolError`, never trusted data. The parity
  test asserts the consumed type/format/nullability constraints and the Problem media type/schema
  against the committed contract, not only field presence. This keeps the hand-maintained projection
  safe without a shared domain model (CR-WEB-MEDIUM-001).
- **Cancellation and explicit failure states.** The query `AbortSignal` is threaded to `fetch`;
  each contracted status, timeout, network, abort, and invalid response is handled distinctly, with
  a bounded Retry-After for 429 and diagnostics separated from user copy (CR-WEB-MEDIUM-002).
- **Browser-security and cache headers.** The SPA is served with a strict same-origin CSP
  (`object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, no `unsafe-inline`/`unsafe-eval`),
  nosniff/referrer/permissions/frame headers, a `no-cache` HTML shell, and `immutable` fingerprinted
  assets — mandatory because the bearer token lives in `sessionStorage` (CR-WEB-MEDIUM-003).
- **Least-privilege runtime.** The static image runs as a non-root user (UID 10001) on an
  unprivileged port with a read-only filesystem, `no-new-privileges`, and all capabilities dropped;
  the Caddy binary's `cap_net_bind_service` is stripped since a low port is not used (CR-WEB-LOW-001).
- **Supply-chain posture.** The toolchain is upgraded to patched Vite/Vitest/React Router (audit
  clean); dev/preview servers bind to loopback and CI fails on a high/critical advisory
  (CR-WEB-MEDIUM-004).

## Consequences

- The compose stack gains a `web_frontend` service (built from `apps/web-frontend/Dockerfile`) and
  the edge reverse proxy now publishes the SPA and the BFF from one origin; the BFF remains the only
  API and the reverse proxy the only host-published port.
- Node.js becomes a build/test-time dependency (CI `frontend` job, image build stage) but not a
  production runtime.
- The frontend depends only on the stable BFF HTTP contract and permission-claim strings, not on any
  service's code or database (ADR-004/007). Contract drift is caught by updating the projected types
  (and the BFF's own conformance test upstream).
- Later frontend subtasks (01E-3 manual registration, 01E-4 card/comments/decision/close) extend
  this foundation without new backend changes.
