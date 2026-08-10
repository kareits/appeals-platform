# web-frontend

The web frontend of the MFO Appeals Platform: a React + TypeScript single-page application. It is
the operator UI and talks only to the BFF gateway over the same-origin `/api/v1` surface. Delivered
incrementally across the EP-1 frontend subtasks; through TASK_01E-3 it covers dev-login, the appeal
list with search/filter, and manual appeal registration.

## Scope (TASK_01E-2, TASK_01E-3)

- Dev/local login (`POST /api/v1/auth/login` via the BFF) and session handling.
- Appeal list with search and filters (`GET /api/v1/tickets` via the BFF), with pagination.
- Manual appeal registration (`POST /api/v1/tickets` via the BFF) with client-side validation of
  required fields, nullable demographic (conditional) fields, and reference-code selects populated
  from `GET /api/v1/reference-data` (TASK_01E-3).
- UI text in the localization layer (Russian and Kazakh), per ADR-015.

The appeal card with comments/decision/close (01E-4) is added in a later subtask.

## Tech stack

- **React 18 + TypeScript**, built with **Vite** (ADR-002). Node.js is a build/test-time tool only;
  the runtime artifact is static files served by Caddy — no Node runs in production.
- **TanStack Query** for server-state (caching, loading/error states, pagination).
- **React Router** for routing and the authentication guard.
- **react-i18next** for localization; all user-facing copy lives in `src/i18n/locales/*.json`.
- **Vitest + Testing Library** for component tests.

## Layout

```
src/
  api/          Transport types (projected from the BFF contract) and the fetch client + endpoints.
  auth/         Session model, persistence, and the auth context (login/logout, permissions).
  components/   Shared UI (app shell, language switcher).
  features/
    login/      Login page.
    tickets/    Appeal list, search form, results table, the manual-registration form/page, and the
                search/reference-data/create hooks.
  i18n/         i18next setup and the ru/kk dictionaries.
  lib/          Small formatting helpers.
  routing/      The authentication route guard.
  test/         Test utilities (provider wrapper, fetch stub).
```

## Local development

Prerequisite: the platform stack running (so the BFF is reachable). Bring it up from the repo root
(use `HTTP_PORT=8090` if 8080 is taken):

```bash
docker compose -f infrastructure/docker-compose.yml up -d
```

Then run the dev server; it proxies `/api` to the edge (override the target for a non-default port):

```bash
cd apps/web-frontend
npm install
npm run dev            # http://localhost:5173
# VITE_API_PROXY_TARGET=http://localhost:8090 npm run dev   # when HTTP_PORT=8090
```

Sign in with a seeded dev user (see the IAM service seed), for example `employee` /
`changeme-dev-01`.

## Quality gates

```bash
npm run lint          # ESLint
npm run format:check  # Prettier
npm run typecheck     # tsc --noEmit
npm test              # Vitest (component + unit tests)
npm run build         # tsc + Vite production build
```

CI runs the same gates in the `frontend` job.

## Configuration

| Variable                | Purpose                                                   | Default                 |
| ----------------------- | --------------------------------------------------------- | ----------------------- |
| `VITE_API_PROXY_TARGET` | Dev-server proxy target for `/api` (build/dev-time only). | `http://localhost:8080` |

The app calls the gateway on the same origin at `/api/v1`; in production the edge reverse proxy
routes `/api` to the BFF and serves everything else from this SPA. There is no runtime configuration
baked into the bundle. The dev and preview servers bind to loopback only.

## Runtime hardening

The production image runs as a non-root user (UID 10001) on the unprivileged port 8080, with a
read-only root filesystem (writable tmpfs only), `no-new-privileges`, and all Linux capabilities
dropped. Every response carries a strict same-origin Content-Security-Policy plus nosniff, frame,
referrer, and permissions headers; the HTML shell is served `no-cache` and fingerprinted assets are
`immutable`. Runtime responses are validated (never trusted via `as T`), and the shared query cache
is scoped per authenticated user and cleared on logout/401 so no data crosses sessions.

## Known limitations

- No individual appeal card yet (opening a row is delivered in 01E-4).
- The dev/local login is temporary (docs/06); corporate OIDC replaces it later (TASK_06). The token
  is held in `sessionStorage` for the tab session only.
- Styling is intentionally minimal; a design system is out of scope for this milestone.
