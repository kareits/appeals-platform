# web-frontend

The web frontend of the MFO Appeals Platform: a React + TypeScript single-page application. It is
the operator UI and talks only to the BFF gateway over the same-origin `/api/v1` surface. Delivered
incrementally across the EP-1 frontend subtasks; through TASK_01E-5 it covers dev-login, the appeal
list with search/filter, manual appeal registration, and the appeal card with comments and commands,
all presented through a consistent design system with light/dark theming and WCAG-AA accessibility.

## Scope (TASK_01E-2 … TASK_01E-4)

- Dev/local login (`POST /api/v1/auth/login` via the BFF) and session handling.
- Appeal list with search and filters (`GET /api/v1/tickets` via the BFF), with pagination.
- Manual appeal registration (`POST /api/v1/tickets` via the BFF) with client-side validation of
  required fields, nullable demographic (conditional) fields, and reference-code selects populated
  from `GET /api/v1/reference-data` (TASK_01E-3).
- Appeal card (`/tickets/:ticketId`) reading the aggregated workspace
  (`GET /api/v1/tickets/{id}/workspace`): the regulatory detail read-only, applicants, comments, and
  the card commands — edit details, re-classify, record decision, close, set/clear legal hold, and
  add comment. Each command is gated by its permission claim, so a first-line read-only user sees the
  card and comments with no editing controls; commands use `expectedVersion` optimistic locking, and
  the close form enforces the regulatory "response date or a recorded reason" rule client-side
  (TASK_01E-4).
- UI text in the localization layer (Russian and Kazakh), per ADR-015.

## Design system (TASK_01E-5, ADR-0011)

- **Design tokens** (`src/styles/tokens.css`): color, spacing, typography, radius, shadow, and focus
  values as CSS custom properties — the single source of truth, with no colors/sizes hard-coded in
  component CSS. `src/styles/base.css` holds the reset and base element styling; `components.css` the
  component and screen styling.
- **Shared components** (`src/components/ui`): presentation-only `Button`, `Field`, `Input`,
  `Select`, `Textarea`, `Badge`, `Alert`, and an accessible modal `Dialog` (ARIA modal contract,
  focus trap, Escape/backdrop dismissal, focus restore). `badgeTone` maps appeal status/priority to a
  semantic color. Later frontend screens (02E-\*, 05B/05C) reuse these.
- **Theming**: light/dark/system. The default follows `prefers-color-scheme`; a header toggle
  (`ThemeToggle`) forces light or dark via a `data-theme` attribute on the document element (not an
  inline style, so the CSP holds) and persists the choice in `localStorage`.
- **Accessibility (WCAG-AA)**: associated labels with `aria-invalid`/`aria-describedby` error wiring,
  visible `:focus-visible` rings, an accessible dialog, responsive layout (wrapping header,
  scrollable tables, single-column commands on narrow viewports), and `prefers-reduced-motion`
  support. An automated `axe-core` check runs over the four core screens in the test suite
  (`src/a11y.test.tsx`); contrast is excluded from the jsdom run and guaranteed by the token palette.

This is a presentation-only layer: no API/contract, business-logic, authorization, or
localization-content change (ADR-0011 supersedes ADR-0009's minimal-styling scope).

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
  components/   App shell, language switcher, theme toggle; ui/ holds the shared design-system
                primitives (Button/Field/Input/Select/Textarea/Badge/Alert/Dialog).
  features/
    login/      Login page.
    tickets/    Appeal list, search form, results table, the manual-registration form/page, the
                appeal card page with its command forms and comments, and the
                search/reference-data/create/workspace/command hooks and value builders.
  i18n/         i18next setup and the ru/kk dictionaries.
  lib/          Small formatting helpers.
  routing/      The authentication route guard.
  styles/       Design-system CSS: tokens.css, base.css, components.css (imported via styles.css).
  theme/        Theme choice (light/dark/system): storage, apply-to-document, and the useTheme hook.
  test/         Test utilities (provider wrapper, fetch stub, axe helper).
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

- Status/stage are placeholder in EP-1 (no Flowable): the card displays them but the app never
  changes them; the workspace process/mail/documents sections are `not_implemented` placeholders
  until later phases.
- The dev/local login is temporary (docs/06); corporate OIDC replaces it later (TASK_06). The token
  is held in `sessionStorage` for the tab session only.
- The axe accessibility check runs in jsdom, which cannot evaluate color contrast. Contrast is
  guaranteed by the WCAG-AA token palette and enforced by a dedicated token-contrast unit test
  (`src/styles/contrast.test.ts`, both themes); a visual pass in the browser is still recommended.
