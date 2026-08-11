# ADR-0011: Frontend design system — CSS design tokens, shared components, theming, and accessibility

- **Status:** Accepted
- **Related:** ADR-0009 (web-frontend foundation — supersedes its deliberate "minimal styling, no
  design system" scope; all other ADR-0009 decisions stand); ADR-002 (approved stack: React +
  TypeScript); ADR-015 (language policy — user-facing Russian/Kazakh text stays in the localization
  layer); ADR-0007/0008 (gateway and Ticket-service authorization — unchanged by this presentation
  work)

## Context

TASK_01E-2 through 01E-4 delivered the EP-1 operator screens (login, appeal list/search, manual
registration, and the appeal card with comments and the decision/close commands) with intentionally
minimal, dependency-free styling; ADR-0009 explicitly deferred a design system. TASK_01E-5 replaces
that MVP styling with a consistent visual design and accessibility pass over the same screens, and
must establish a reusable system that the later frontend screens (02E-\*, 05B/05C) inherit. This is a
presentation-only change: no API/contract, business-logic, authorization, or localization-content
changes, and the ADR-015 user-facing text layer stays intact.

A hard constraint carries over from ADR-0009's security hardening: the SPA is served under a strict
same-origin Content-Security-Policy with `style-src 'self'` and `script-src 'self'` — no
`unsafe-inline` and no `unsafe-eval`. That rules out any styling approach that injects inline
`<style>` tags or `style=` attributes at runtime (runtime CSS-in-JS such as styled-components or
emotion, and the component libraries built on them). The bearer token also lives in `sessionStorage`,
so the design system must not weaken that posture (no new remote asset origins, no inline scripts).

## Decision

- **Plain CSS design tokens as the single source of truth.** Color, spacing, typography, radius,
  shadow, and focus values are defined once as CSS custom properties in `src/styles/tokens.css`;
  base element styling/reset lives in `src/styles/base.css` and component/screen styling in
  `src/styles/components.css`. No colors, sizes, or fonts are hard-coded in component CSS. This adds
  **zero runtime dependencies**, is fully compatible with the strict CSP (a single self-hosted,
  fingerprinted stylesheet under `'self'`), and keeps `npm audit` clean — the decisive advantages
  over a utility framework (new build tooling and supply chain) or a component library (runtime
  CSS-in-JS conflicts with the CSP; heavier supply chain).
- **A small shared component layer.** `src/components/ui` provides presentation-only wrappers —
  `Button`, `Field`, `Input`, `Select`, `Textarea`, `Badge`, `Alert` — plus an accessible modal
  `Dialog`, backed by the token CSS classes. They standardize look and accessibility (for example
  `Field` wires `aria-invalid`/`aria-describedby` to the control's error and hint) without changing
  behavior, so the existing role/label/text contracts the screens and tests rely on are preserved.
  `Badge` colors appeal status and priority via a reusable `badgeTone` mapping; `Dialog` implements
  the ARIA modal contract (`role="dialog"`, `aria-modal`, labelled by its title) with focus move-in,
  a Tab focus trap, Escape/backdrop dismissal, and focus restoration.
- **Theme-aware (light/dark/system) via tokens and a `data-theme` attribute.** The default follows
  the OS through `prefers-color-scheme`; an in-app toggle forces light or dark by setting a
  `data-theme` attribute on the document element (never an inline style, so the CSP holds) and
  persists the choice in `localStorage` (a non-sensitive UI preference, unlike the bearer token in
  `sessionStorage`). All token color pairs used for text meet WCAG-AA contrast in both themes.
- **Accessibility to WCAG-AA.** Visible `:focus-visible` focus rings, associated labels and error
  messaging, an accessible dialog, responsive layout (wrapping header, horizontally scrollable
  tables, single-column command grid on narrow viewports), and `prefers-reduced-motion` support. An
  automated axe check (`axe-core`) runs in the existing Vitest/jsdom suite over the four core screens
  and asserts no WCAG A/AA structural violations. Contrast is excluded from the jsdom axe run (it
  cannot compute resolved colors); it is instead guaranteed by the token palette and enforced by a
  dedicated unit test (`src/styles/contrast.test.ts`) that parses the tokens and asserts every
  text/button color pair meets the 4.5:1 normal-text ratio in **both** light and dark themes.

## Alternatives considered

- **Tailwind CSS (build-time utility framework):** rejected for this task — it is CSP-safe
  (compiled, no inline styles) but adds new build tooling (`tailwindcss`/`postcss`/`autoprefixer`)
  and supply chain for a small four-screen surface, and utility classes in markup buy little over a
  focused token set. Revisit if the frontend grows enough that utilities pay off.
- **A component library (MUI, Chakra, etc.):** rejected — most render through runtime CSS-in-JS
  (emotion), which needs `style-src 'unsafe-inline'` and would force weakening the ADR-0009 CSP, plus
  a heavy dependency footprint against the `npm audit` gate.
- **CSS Modules or a CSS-in-JS build plugin:** rejected as unnecessary — the surface is small enough
  that a single tokenized stylesheet with BEM-ish class names is clear, and it avoids extra tooling.
- **A real-browser axe run (Playwright):** deferred — it would evaluate contrast too, but adds a new
  browser-based test infrastructure disproportionate to this task; token-guaranteed contrast plus the
  jsdom structural axe check is sufficient here.

## Consequences

- The four EP-1 screens are restyled through the token layer and the shared components without
  changing their API calls, permission gating, validation, or localized copy; existing behavior and
  component tests stay green, and new axe and Dialog tests are added.
- `axe-core` is added as a build/test-time dev dependency only; no runtime dependency and no new
  asset origin are introduced, so the ADR-0009 CSP and least-privilege runtime are unchanged.
- Later frontend screens (02E-\*, 05B/05C) reuse the same tokens and components for a consistent look
  instead of restyling ad hoc.
- ADR-0009's "minimal styling, no design system" scope is superseded by this ADR; every other
  ADR-0009 decision (SPA stack, gateway-only access, same-origin edge routing, session handling, CSP
  and least-privilege hardening) remains in force.
