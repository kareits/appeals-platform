# SERVICE_MAP — bff-service

Structured map of the BFF (API gateway) service. Kept current as behavior changes (Definition of
Done, root `CLAUDE.md`).

## Responsibility

The single API the web frontend talks to (BFF_SERVICE spec). Establishes the caller's auth context
from IAM, enforces permission claims at the gateway, aggregates the appeal workspace from downstream
services, normalizes errors (RFC 7807), and propagates the correlation ID. Owns no domain data and
duplicates no business logic.

## Owned data

None. The gateway keeps its own database/user to reserve its schema boundary (ADR-004); the baseline
migration creates no tables. Future state (for example, rate-limit counters) is added as a new
migration.

## API

Base path `/api/v1`, JSON camelCase, RFC 7807, `X-Correlation-ID`. Contract:
`contracts/openapi/bff-service.v1.yaml`, served verbatim at `/openapi.json`. Proxied operations
project the exact upstream transport schemas from `iam-service.v1.yaml`/`ticket-service.v1.yaml`;
`tests/test_bff_downstream_conformance.py` asserts the dereferenced cross-contract match and fails
on upstream drift.

| Method | Path | Description | Required permission |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Login → access token (relays IAM) | none |
| GET | `/api/v1/auth/me` | Caller's resolved auth context | authenticated |
| GET | `/api/v1/tickets` | Search appeals (relays Ticket) | `ticket:read` |
| POST | `/api/v1/tickets` | Register an appeal (relays Ticket) | `ticket:create` |
| GET | `/api/v1/tickets/{ticketId}/workspace` | Aggregated workspace | `ticket:read` |
| PATCH | `/api/v1/tickets/{ticketId}` | Update card details | `ticket:update` |
| POST | `/api/v1/tickets/{ticketId}/classify` | Set classification | `ticket:classify` |
| POST | `/api/v1/tickets/{ticketId}/decision` | Record decision | `ticket:decide` |
| POST | `/api/v1/tickets/{ticketId}/close` | Close appeal | `ticket:close` |
| POST | `/api/v1/tickets/{ticketId}/legal-hold` | Set/clear legal hold | `ticket:legal_hold` |
| POST | `/api/v1/tickets/{ticketId}/comments` | Add comment | `ticket:comment` |
| GET | `/api/v1/reference-data` | List reference-dictionary entries (relays Ticket) | `ticket:read` |
| GET | `/health/live` | Liveness | none |
| GET | `/health/ready` | Readiness (own database) | none |

## Auth context and enforcement

- Auth context is resolved by calling IAM `GET /api/v1/auth/me` with the caller's bearer token
  (`application/auth_context.py`); the gateway holds no signing material.
- Permission enforcement checks the resolved `resource:action` claim strings
  (`domain/permissions.py`, `api/dependencies.require_permission`); the role→permission matrix is
  not reimplemented (ADR-007). Enforcement is defence in depth — the Ticket Service independently
  authenticates and authorizes every request as well (ADR-0008).

## Workspace aggregation

`GET /tickets/{id}/workspace` (`application/workspace.py`) reads the card and comments concurrently
under a total request deadline. Failures are classified explicitly, never masked as `200 degraded`:
card/comments 401→401, 403→403; card 404→404; card 429→429 (Retry-After preserved); card timeout→504;
card connection failure→503; card 5xx/malformed→502. Only the optional `comments` section degrades
(`unavailable`, `degraded=true`) on a non-auth failure. The process/mail/documents sections are
`not_implemented` placeholders.

## Error normalization and bounded I/O (safe relay)

Forwarded command/search responses are relayed under a narrow policy (`api/proxy.relay`): 2xx JSON is
relayed only under an exact `application/json` media type; documented client errors become sanitized
RFC 7807 Problem Details; 5xx/unexpected/near-miss-media/malformed become a gateway 502; timeouts 504
and connection failures 503. Only an allowlist of protocol headers is propagated; downstream 5xx
bodies, internal URLs, and stack traces never cross the boundary.

Memory is bounded at both edges (`api/proxy.read_body_bounded` + `mfo_http.read_bounded`): an
incoming body over `BFF_MAX_REQUEST_BYTES` is rejected with `413` before full buffering and before
any downstream call; every downstream response is streamed and abandoned as a `502` if it exceeds
`BFF_MAX_RESPONSE_BYTES`. Caddy enforces an outer request-body ceiling. Cancellation propagates; it
is never converted into a partial success.

## Emitted events

None. The gateway publishes no events.

## Consumed events

None. The gateway is request/response only.

## External dependencies

- IAM service (HTTP) — auth context and login proxy (`BFF_IAM_BASE_URL`).
- Ticket Service (HTTP) — search, commands, workspace reads (`BFF_TICKET_BASE_URL`).
- PostgreSQL — the gateway's own (empty) database in compose; SQLite for local runs and unit tests.

## Failure behavior

- Missing/empty bearer token → 401; IAM rejects the token → 401; IAM unreachable/timeout → 503; a
  malformed IAM identity response (wrong media type, invalid JSON, invalid claims) → safe 502.
- Caller lacks the required permission → 403 (before any downstream call).
- Ticket Service unreachable on a forwarded call → 503, timeout → 504; downstream client-error
  statuses (400/401/403/404/409/422/429) are preserved but their bodies are **not** relayed verbatim
  — the gateway substitutes a safe status-derived RFC 7807 title and drops downstream detail text;
  5xx/unexpected/malformed responses become a safe 502.
- Workspace: a downstream 401/403 → 401/403; missing appeal → 404; card 429 → 429; card timeout →
  504; card connection failure → 503; card 5xx/wrong-media/invalid-shape/oversized → 502. Only the
  optional comments section degrades (200 with `degraded=true`); critical/auth failures are not
  masked as success.
- `/health/ready` → 503 when the gateway's own database is unreachable. Downstream reachability is
  intentionally excluded from readiness.

## Migrations

Alembic; apply with `cd services/bff_service && uv run alembic upgrade head`.

- **migration:** `0001_baseline` establishes the gateway's own schema baseline; it creates no domain
  tables (only Alembic's bookkeeping table).
- **backfill:** none.
- **rollback:** `alembic downgrade base` (no-op; nothing to drop).
- **validation:** `test_bff_migration` applies to head, asserts the Alembic version table exists, and
  reverts to base.
- **compose:** a one-shot `bff_migrate` service runs `alembic upgrade head` before `bff_service`
  starts.

## Testing

`uv run pytest services/bff_service`. Downstream services are faked with `httpx.MockTransport`.

## Known limitations

- Gateway enforcement is defence in depth; the Ticket Service also verifies the forwarded token and
  enforces its own permission/data-scope policy (ADR-0008).
- The Ticket data-scope policy is a minimal fail-closed EP-1 baseline (ADR-0008); the full business
  matrix is pending.
- Process/mail/documents workspace sections are placeholders until their services exist.
- No rate limiting yet (the empty owned schema leaves room to add it later).
