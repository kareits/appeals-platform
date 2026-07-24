# ADR-0008: Ticket-service independent authorization, data scope, and trusted actor

- **Status:** Accepted
- **Related:** ADR-0006 (dev-auth and the authorization matrix); ADR-0007 (BFF gateway); ADR-004
  (data boundaries); ADR-007 (shared-library boundaries); docs/06 (RBAC, audit); the independent
  review CR-BFF-BLOCKER-001 (CODE_REVIEW_REPORT §22)

## Context

The independent review of TASK_01E-1 showed the Ticket Service performed no authentication or
authorization: a direct internal call read an appeal without a token, and a comment was stored under
a caller-supplied author UUID. Gateway-only checks in the BFF are not a security boundary for a
coarse-grained microservice architecture (ADR-002): any workload on the internal network can call
the Ticket Service directly. The service must enforce its own boundary (CR-IAM-HIGH-003; the
original CR-HIGH-001/IDOR and trusted-actor requirements).

The full business matrix for team/department/confidentiality scoping is not yet approved. Per the
review, where the matrix is undefined the service must implement a **minimal, fail-closed** EP-1
policy, document the assumptions, and never grant broader access by default.

## Decision

- **Independent authentication.** The Ticket Service verifies the IAM-issued access token itself
  (`infrastructure/auth_tokens.py`): a fixed algorithm allowlist (HS256; no `alg=none`/confusion),
  and verification of signature, issuer, audience, expiry, the subject UUID, and the structural types
  of every claim. It does **not** import IAM code or read the IAM database (ADR-004); only the claim
  strings are a shared wire contract. A missing/invalid token is 401 with `WWW-Authenticate: Bearer`.
- **Independent permission enforcement.** Every route requires a specific `resource:action` claim
  (`domain/permissions.py`, `api/dependencies.require_permission`); the service checks the claim
  strings and does not reimplement the IAM role→permission matrix (ADR-007). A missing permission is
  403. Consequently **ADMIN** (which holds only `iam:manage`) has no ticket permissions and is denied
  every ticket route, and **FIRST_LINE_READONLY** (only `ticket:read`) cannot mutate.
- **Object-level data scope (fail-closed EP-1 policy, `domain/authorization.py`).** After the
  permission gate, access to a specific appeal is decided from the caller's roles and teams:
  - Oversight/analytics/audit roles (**SUPERVISOR, OMBUDSMAN, ANALYST, AUDITOR**) read across teams.
  - Operational roles (**EMPLOYEE, FIRST_LINE_READONLY**) reach an appeal only when it is in one of
    their teams, assigned to them, or registered by them.
  - **Confidential** appeals are visible only to **SUPERVISOR, OMBUDSMAN, AUDITOR**; confidentiality
    overrides team/assignment/registration (an owning employee cannot read back a confidential
    appeal they registered). This is fail-closed.
  - Search is constrained by the same scope, so a team-scoped caller cannot enumerate other teams'
    appeals. An authenticated caller without scope receives 403 (existence is not treated as
    sensitive in EP-1; missing appeals are 404).
  - Team membership travels in a new `teams` token claim issued by IAM (a user currently belongs to
    at most one team). Two new ticket columns back the policy: `registered_by` (the verified
    registrant, server-derived) and `is_confidential`.
- **Separate read and mutation scope (CR-BFF-RR-HIGH-001).** Object scope is evaluated per mode, not
  once: mutation uses strictly narrower role sets than read, so combining roles cannot manufacture an
  unapproved composite capability. Controlled read/audit roles (ANALYST, AUDITOR) contribute **read**
  scope only and never mutation scope; the confidential-mutation set (SUPERVISOR, OMBUDSMAN) is
  narrower than the confidential-read set (adds AUDITOR). A caller holding `AUDITOR + EMPLOYEE`
  therefore cannot mutate a confidential or other-team ticket, even though one role supplies the
  mutation permission and the other supplies broad read scope.
- **Per-caller idempotency (CR-BFF-RR-BLOCKER-001).** The client `Idempotency-Key` is namespaced to
  the authenticated subject (stored as a SHA-256 of `"<subject>:<key>"`), so it is a per-caller
  namespace, never a global object-lookup oracle: a second user replaying another user's key gets
  their own new ticket, never the first user's. A request fingerprint is stored so that reusing a key
  with a different payload is a 409 conflict rather than a silent replay; authorization is applied
  before returning any existing object on both the normal and concurrency-recovery paths.
- **Fail-closed classification backfill (CR-BFF-RR-HIGH-002).** Migration 0005 backfills every
  pre-existing appeal (whose regulated classification was never evaluated) to `is_confidential = TRUE`
  so it is treated as confidential until an authorized process reclassifies it; unknown classification
  is never interpreted as public.
- **Trusted server-derived actor.** `decisionBy`, `actorId`, and `authorId` are removed from the
  public request contracts. The deciding employee, the comment author, the registrant, and every
  audit actor are the verified token subject, never client input. Mutation, audit, and outbox writes
  remain in one transaction (unchanged).

Department scope is not modeled in EP-1; the team is the (narrower, fail-closed) scope unit until the
business matrix defines departments.

## EP-1 assumptions (to be replaced by the approved business matrix)

1. The four oversight/analytics/audit roles have organization-wide read of non-confidential appeals.
2. Operational roles are limited to their team, assignments, and registrations.
3. The confidential-access set is SUPERVISOR/OMBUDSMAN/AUDITOR.
4. A missing scope yields 403 (not a 404 existence-hiding response).
5. `registered_by` grants the registering employee ongoing access until Flowable assigns a
   team/assignee (EP-3); this slightly extends the "assignment comes from Flowable" model for EP-1
   and is revisited when projection-driven assignment lands.

These are deliberately narrow and fail closed; none widens access by default. They must be confirmed
against the business RBAC/confidentiality matrix before pilot.

## Alternatives considered

- **Keep gateway-only enforcement (BFF).** Rejected — not a boundary for internal callers; the
  review demonstrated a direct bypass. Gateway checks remain as defence in depth (ADR-0007).
- **Call IAM to authorize each request.** Rejected for the Ticket Service — self-contained claim
  verification avoids an availability dependency and matches ADR-0006's downstream-verification
  rationale. (Revocation/live-state checks are separate future work.)
- **Model confidentiality/organization scope now with the full business matrix.** Deferred — the
  matrix is not approved; a fail-closed minimal policy is implemented and documented instead.
- **Keep caller-supplied actor fields for backward compatibility.** Rejected — they are forgeable and
  reached audit; they are removed outright (there is no external consumer yet).

## Consequences

- The Ticket Service is a self-standing security boundary: authenticated, permission-checked, and
  data-scoped on every route, including direct internal calls.
- Audit attribution is trustworthy (server-derived actor).
- The `teams` claim is now part of the token contract (additive); IAM issues it, and downstream
  services may use it for scope.
- The EP-1 scope policy is intentionally coarse and fail-closed; broadening it requires the approved
  business matrix, and the assumptions above are the explicit record of what must be confirmed.
- Production still requires corporate OIDC/asymmetric verification and separated credentials
  (ADR-AUTH-OIDC, TASK_06); the shared symmetric secret is a dev/local scheme only.
