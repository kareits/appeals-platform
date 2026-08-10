# BFF Service

Backend-for-Frontend — the single API the web frontend of the MFO Appeals Platform talks to
(TASK_01E-1). The gateway establishes the caller's **auth context** from the IAM service, enforces
**permission claims** at the gateway, **aggregates** the appeal workspace from downstream services,
and **normalizes errors** as RFC 7807 Problem Details. It owns no domain data and duplicates no
business logic (BFF_SERVICE spec). See
[`docs/adr/ADR-0007-bff-gateway.md`](../../docs/adr/ADR-0007-bff-gateway.md).

## How it works

- **Auth context via IAM `/auth/me`.** The gateway does not verify tokens itself; it resolves the
  caller's subject, roles, and permissions by calling IAM with the presented bearer token. This
  keeps signing material out of the gateway and stays valid across the corporate OIDC transition
  (ADR-AUTH-OIDC, TASK_06).
- **Permission enforcement on claim strings.** Protected routes require a specific `resource:action`
  claim; the gateway checks the claim strings on the resolved context and does not reimplement the
  IAM role→permission matrix (ADR-007). An under-privileged caller is rejected before any downstream
  call. This is **defence in depth**: the Ticket Service independently authenticates and authorizes
  every request as well (ADR-0008), so a direct call that bypasses the gateway is still enforced.
- **Workspace aggregation with explicit failure classification.** The workspace envelope carries the
  appeal card and comments plus `not_implemented` placeholders for the process, mail, and documents
  flows (later phases). Failures are not masked as `200 degraded`: a downstream 401/403 on the card
  or comments surfaces as 401/403, a missing appeal is 404, a card timeout is 504, a card connection
  failure is 503, and a card 5xx or malformed body is a safe 502. Only the optional `comments`
  section degrades (marked `unavailable`, `degraded=true`) on a non-auth failure.
- **Forwarding with safe error normalization.** Ticket command/search requests are forwarded (body,
  query, bearer token, idempotency key), but responses are **not** echoed verbatim: successful JSON
  is relayed (size-bounded, exact `application/json` media type only); documented client errors
  become sanitized RFC 7807 Problem Details reconstructed from allowed fields; any 5xx, unexpected
  status, near-miss media type (`application/jsonp`, `text/application/json`), oversized, or
  malformed body becomes a safe gateway 502; a downstream timeout is 504 and a connection failure
  503. Only an allowlist of protocol headers (`WWW-Authenticate`, `Retry-After`, `Location`, `ETag`)
  is propagated, and the correlation ID is on every response. Internal URLs, stack traces, and SQL
  never cross the boundary.
- **Bounded memory at the trust boundary.** Incoming login/mutation bodies are read incrementally and
  rejected with a sanitized `413` before full buffering (and never partially forwarded); the outer
  Caddy proxy enforces its own request-body ceiling. Every downstream response (login, search,
  commands, auth-context, workspace) is streamed under a hard byte ceiling via the shared
  `mfo_http.read_bounded` helper and abandoned as a safe `502` if it exceeds the limit, so a faulty
  or hostile upstream cannot exhaust gateway memory. Limits are configurable
  (`BFF_MAX_REQUEST_BYTES`, `BFF_MAX_RESPONSE_BYTES`).

## API

Base path `/api/v1`, JSON with camelCase fields, RFC 7807 Problem Details, `X-Correlation-ID`
propagation. Contract:
[`contracts/openapi/bff-service.v1.yaml`](../../contracts/openapi/bff-service.v1.yaml).

The contract is the runtime OpenAPI document served verbatim at `/openapi.json` (the committed file
is baked into the image). For every proxied operation (login and the Ticket commands/search) it
projects the exact upstream transport schema from `iam-service.v1.yaml`/`ticket-service.v1.yaml`
— request/response bodies, required fields, enums, nullability, constraints and
`additionalProperties` — so the frontend sees the concrete wire contract rather than an open-ended
object. The conformance test also verifies the relayed downstream error statuses (including `400`),
the gateway-added `413`/`502`/`503`/`504` responses, the `application/problem+json` RFC 7807 shape of
every error, the `X-Correlation-ID` header on every response, and the full security requirement, with
negative drift tests that fail on any upstream/BFF change. This is a transport projection only, never
a shared domain-model library.

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Login → access token (relays IAM) | none (dev-only) |
| GET | `/api/v1/auth/me` | Caller's resolved auth context | bearer token |
| GET | `/api/v1/tickets` | Search appeals | `ticket:read` |
| POST | `/api/v1/tickets` | Register an appeal | `ticket:create` |
| GET | `/api/v1/tickets/{ticketId}/workspace` | Aggregated appeal workspace | `ticket:read` |
| PATCH | `/api/v1/tickets/{ticketId}` | Update editable card details | `ticket:update` |
| POST | `/api/v1/tickets/{ticketId}/classify` | Set classification | `ticket:classify` |
| POST | `/api/v1/tickets/{ticketId}/decision` | Record the decision | `ticket:decide` |
| POST | `/api/v1/tickets/{ticketId}/close` | Close the appeal | `ticket:close` |
| POST | `/api/v1/tickets/{ticketId}/legal-hold` | Set/clear legal hold | `ticket:legal_hold` |
| POST | `/api/v1/tickets/{ticketId}/comments` | Add a comment | `ticket:comment` |
| GET | `/api/v1/reference-data` | List reference-dictionary entries (relays Ticket) | `ticket:read` |
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (own database) | none |

## Configuration

Environment variables use the `BFF_` prefix (see [`config.py`](src/bff_service/config.py)):

| Variable | Default | Purpose |
|---|---|---|
| `BFF_ENVIRONMENT` | `local` | Deployment environment name. |
| `BFF_DATABASE_URL` | SQLite file | Async SQLAlchemy URL for the gateway's own (empty) schema (PostgreSQL in compose). |
| `BFF_IAM_BASE_URL` | `http://localhost:8000` | IAM service base URL (auth context + login). |
| `BFF_TICKET_BASE_URL` | `http://localhost:8000` | Ticket Service base URL (search, commands, workspace). |
| `BFF_HTTP_CONNECT_TIMEOUT_SECONDS` | `5.0` | Per-call connect timeout (bounded, positive, finite). |
| `BFF_HTTP_READ_TIMEOUT_SECONDS` | `10.0` | Per-call read timeout. |
| `BFF_HTTP_WRITE_TIMEOUT_SECONDS` | `10.0` | Per-call write timeout. |
| `BFF_HTTP_POOL_TIMEOUT_SECONDS` | `5.0` | Timeout waiting for a pooled connection. |
| `BFF_WORKSPACE_DEADLINE_SECONDS` | `15.0` | Total budget for the concurrent workspace aggregation. |

## Owned data

None. The gateway keeps its own database/user only to reserve its schema boundary (ADR-004); the
baseline migration creates no tables. It performs no cross-service database access (ADR-004/007).

## Local development

```bash
# Sync the workspace (all packages + dev deps) from the repo root.
python -m uv sync --all-packages --dev

# Apply the baseline migration against the configured database (creates only Alembic bookkeeping).
cd services/bff_service && python -m uv run alembic upgrade head

# Run the service (point it at running IAM and Ticket services).
python -m uv run uvicorn bff_service.main:app --reload
```

## Testing

```bash
python -m uv run pytest services/bff_service
```

Covers the auth context (resolve, missing/rejected token, IAM outage → 503), the login proxy,
workspace aggregation (success, 404, flagged partial failure, permission denial), gateway
passthrough (body/token/idempotency-key/correlation-id forwarding, permission enforcement,
downstream Problem Details relay, Ticket outage → 503), OpenAPI contract parity, and the baseline
migration. Downstream services are faked with `httpx.MockTransport`, so no real services are needed.

## Compose deployment

In `infrastructure/docker-compose.yml` a one-shot `bff_migrate` service applies the baseline before
`bff_service` starts; the gateway reaches `iam_service` and `ticket_service` on the internal
network. The reverse proxy publishes the BFF as the single host entry point
(`http://localhost:${HTTP_PORT}`). Readiness (`/health/ready`) checks only the gateway's own
database; a downstream outage surfaces on the affected request (401/403/404/502/503/504) but does not
mark the gateway itself unready.

Roles and databases are provisioned by the idempotent one-shot `db_provision` job
(`infrastructure/postgres/provision/provision-databases.sh`), which runs on every startup: it creates
any missing service role/database and reconciles an existing role's password without deleting data,
so an existing (pre-upgrade) `pgdata` volume is brought up to date automatically — no manual SQL and
no volume recreation. The migration jobs depend on it completing. Passwords may contain URI-reserved
characters: the service builds its connection URL from discrete parts with a percent-encoded password
(CR-BFF-R3-MEDIUM-003).

## Known limitations

- Gateway permission enforcement is defence in depth; the Ticket Service independently authenticates
  and authorizes every request (ADR-0008), so both layers enforce access.
- The Ticket data-scope policy is a minimal, fail-closed EP-1 baseline (ADR-0008); the full business
  team/department/confidentiality matrix is not yet approved.
- Dev/local symmetric JWT only; corporate OIDC/asymmetric verification is TASK_06 (ADR-AUTH-OIDC).
- No rate limiting yet; the service keeps an empty database so state (for example, rate-limit
  counters) can be added later as a new migration.
- Process, mail, and documents workspace sections are placeholders until their services exist.
