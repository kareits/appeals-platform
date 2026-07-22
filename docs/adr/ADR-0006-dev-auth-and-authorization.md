# ADR-0006: Dev/local authentication and the authorization matrix

- **Status:** Accepted
- **Related:** DECISION_LOG ADR-AUTH-OIDC (dev-auth → corporate OIDC, TASK_06); ADR-007
  (shared-library boundaries); docs/06 (security, authorization, audit); IAM_SERVICE spec

## Context

TASK_01D introduces the IAM Service: users, roles, teams, and an authorization matrix, with
dev/local authentication available outside production only (docs/06). The platform needs a way for a
subject to authenticate and for downstream services to make authorization decisions, before the
corporate OIDC/SSO integration exists (TASK_06). Two constraints shape the design: docs/06 targets
signed-JWT verification with separated user/service credentials in production, and ADR-007 forbids a
shared permission-rule library — each service must enforce authorization independently.

## Decision

- **Authorization matrix ownership:** the role → permission mapping lives inside the IAM Service
  (`domain/permissions.py`), which owns roles. It is **not** placed in a shared library (ADR-007).
  IAM resolves a subject's roles to a flat set of `resource:action` permission strings; downstream
  services check those claim strings and never import IAM's matrix.
- **Seven roles** (IAM_SERVICE spec): `EMPLOYEE`, `SUPERVISOR`, `FIRST_LINE_READONLY`, `OMBUDSMAN`,
  `ANALYST`, `ADMIN`, `AUDITOR`. The regulatory invariant enforced and tested is that
  `FIRST_LINE_READONLY` is read-only (docs/01): it grants only `ticket:read`. The EP-1 matrix is a
  coarse dev/local baseline; values may be refined later without changing the claim format.
- **Dev token = signed JWT (HS256):** `POST /auth/login` verifies a password against a stored bcrypt
  hash and returns a signed JWT whose claims carry the subject, username, roles, and resolved
  permissions. Self-contained claims let downstream services (the BFF, 01E-1) authorize without
  calling IAM per request. The symmetric HS256 scheme is forward-compatible with the OIDC
  transition (ADR-AUTH-OIDC), which swaps the key material, issuer, and audience without changing
  the claim shape.
- **Password hashing = bcrypt:** docs/06 requires proper password hashing for the temporary auth.
  bcrypt embeds a per-hash salt and a tunable work factor; no salt is stored separately. Passwords
  are never persisted or logged in plaintext.
- **Dev login is allowlisted, fails closed:** dev authentication is available only for the closed
  environment allowlist `local`/`dev`/`test`; any other value — `staging`, `production`, the compose
  `docker` default, or a misspelling such as `Production` — disables it and the login returns 403
  (docs/06). Because environment spelling is a security boundary, the service additionally refuses to
  start when dev auth is enabled outside `local`/`test` with the default or a too-short signing
  secret, so a shared server cannot run with a repository-known key (CR-IAM-HIGH-002).
- **Audit:** logins, user creation, and role changes are written to `iam_audit_log` in the same
  transaction as the change (docs/06 "role changes audited"). IAM emits no `iam.*` domain events —
  that namespace is not in the event catalog (ADR-006).
- **Dev seed:** migration `0002` seeds one user per role (shared well-known dev password) as an
  immutable snapshot; these accounts are non-production only.

## Alternatives considered

- **Opaque session tokens with server-side introspection:** rejected — simpler cryptographically but
  diverges from the docs/06 signed-JWT target and would require rework at TASK_06; self-contained
  JWT claims also avoid a per-request IAM round trip from the BFF.
- **A shared permission-rule library in `libs/`:** rejected — violates ADR-007 service isolation.
  IAM issues claims; each service enforces them independently.
- **argon2 password hashing:** viable and stronger, but adds a native dependency; bcrypt is
  sufficient for the temporary non-production dev login and has no build friction on the target
  platforms.
- **Storing the matrix in a database table (admin-editable):** deferred — the EP-1 baseline is a
  code-level matrix; a configurable store can come with the broader business-policy work.

## Consequences

- Downstream services depend only on stable permission-claim strings, not on IAM role names or code.
- The dev auth is explicitly non-production; TASK_06 replaces it with corporate OIDC and asymmetric
  signing, and removes the insecure default secret and dev seed accounts.
- Changing the seed users/roles or regenerating their password hashes requires a **new** migration,
  never an edit to `0002` (immutable-snapshot rule).
