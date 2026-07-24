# ADR-0007: BFF gateway — auth context, permission enforcement, and workspace aggregation

- **Status:** Accepted
- **Related:** ADR-0006 (dev-auth and the authorization matrix); ADR-004 (data boundaries); ADR-007
  (shared-library boundaries); ADR-AUTH-OIDC (dev-auth → corporate OIDC, TASK_06); BFF_SERVICE spec;
  docs/05 (API/error/correlation conventions)

## Context

TASK_01E-1 introduces the BFF: the single API the web frontend talks to. The frontend must be able
to authenticate, search and register appeals, open an appeal workspace, and record card actions,
without talking to individual services or duplicating their logic. Per the context-loading guide,
the BFF is changed only in 01E-1 (later 01E subtasks touch the frontend only), so the gateway must
expose the full set of endpoints the EP-1 frontend needs. Two constraints shape the design: ADR-004
forbids importing another service's code or database, and ADR-007 forbids a shared permission-rule
library.

## Decision

- **Auth context via IAM `/auth/me`:** the gateway does not verify access tokens itself. It resolves
  the caller's context by calling IAM `GET /api/v1/auth/me` with the presented bearer token. This
  keeps token-signing material out of the gateway and keeps IAM the single authority on claim
  resolution, which stays valid across the corporate OIDC transition (ADR-AUTH-OIDC): only IAM's
  verification changes, not the gateway. An IAM timeout/unreachable maps to 503; a malformed identity
  response (wrong media type, invalid JSON, or invalid claim structure) fails closed as a safe 502.
- **Permission enforcement at the gateway on claim strings:** protected routes require a specific
  `resource:action` permission claim (for example, search/workspace require `ticket:read`; register
  requires `ticket:create`; the card commands require their respective claims). The gateway checks
  the claim strings present on the resolved context; it does **not** reimplement the role→permission
  matrix (ADR-007). This rejects an under-privileged caller (for example, first-line read-only)
  before any downstream call. It is defence in depth: the Ticket Service **also** authenticates and
  authorizes every request independently (ADR-0008), so a direct call bypassing the gateway is still
  enforced.
- **Workspace aggregation with explicit failure classification:** `GET /tickets/{id}/workspace`
  aggregates the appeal card and comments from the Ticket Service into one envelope with per-section
  status, alongside `not_implemented` placeholders for the process, mail, and documents flows
  delivered in later phases. Failures are classified, not masked: a downstream 401/403 on the card or
  comments returns 401/403; a missing appeal returns 404; a card 429 returns 429; a card timeout 504;
  a card connection failure 503; a card 5xx, wrong media type, invalid shape, or oversized body a safe
  502. Only the genuinely optional `comments` section degrades (`unavailable`, `degraded=true`) on a
  non-auth failure — critical/auth failures are never hidden as a `200 degraded`.
- **Forwarding for commands and search under a safe relay policy:** the gateway forwards ticket
  command/search requests (body, query, bearer token, idempotency key) but does not echo downstream
  responses verbatim (see the amendment below). Successful JSON is relayed size-bounded; documented
  client errors are reconstructed as sanitized RFC 7807 Problem Details; 5xx/unexpected/malformed
  responses become a safe gateway 502; timeouts become 504 and connection failures 503. Only an
  allowlist of protocol headers is propagated. The correlation ID is on every response.
- **Stateless with an empty owned schema:** the gateway stores no domain data in EP-1. It keeps its
  own database/user (ADR-004) with a baseline migration that creates no tables, reserving the schema
  boundary; readiness checks only the gateway's own database connectivity. A downstream outage
  degrades a workspace read but must not take the gateway itself out of service, so downstream
  reachability is deliberately excluded from readiness.

## Alternatives considered

- **Verify the JWT inside the BFF (share the signing secret):** rejected — it would spread signing
  material and duplicate IAM's claim resolution, and would need rework when production moves to
  asymmetric OIDC verification. Calling `/auth/me` keeps IAM authoritative.
- **Enforce authorization only downstream (thin proxy):** rejected for the gateway layer — enforcing
  at the gateway rejects under-privileged callers early and gives the frontend a single, consistent
  authorization surface. Downstream enforcement is still required (defence in depth).
- **Model every ticket request/response schema in the BFF contract:** rejected — it would duplicate
  the Ticket Service contract and drift (BFF_SERVICE spec: do not duplicate domain logic). The
  gateway documents only its own shapes (auth context, workspace) and forwards ticket bodies
  verbatim.
- **Fail the whole workspace on any read error:** rejected — it hides which part failed. Flagging the
  affected section and returning the rest matches the spec's partial-failure requirement.
- **Provision domain tables now:** rejected — the gateway has no domain state; adding tables without
  need violates "no infrastructure without need". Persistent state (for example, rate-limit
  counters) is added as a new migration when a feature requires it.

## Consequences

- The frontend has a single authenticated API surface; 01E-2/3/4 change only the frontend.
- The gateway depends on stable IAM/Ticket HTTP contracts and permission-claim strings, not on their
  code or databases (ADR-004/007).
- Gateway permission enforcement is defence in depth; the Ticket Service independently authenticates
  and authorizes every request (ADR-0008), closing the direct-bypass/IDOR risk at its own boundary.
- The compose stack now wires the Ticket and BFF services (and their one-shot migration jobs), and
  the reverse proxy publishes the BFF as the single host entry point.
