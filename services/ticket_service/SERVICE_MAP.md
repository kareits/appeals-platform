# SERVICE_MAP — ticket-service

Structured map of the ticket service. Kept current as behavior changes (Definition of Done, root
`CLAUDE.md`).

## Responsibility

Regulatory registry and appeal card: the ticket model, applicants/representatives, reference
dictionaries, comments, classification, decision, closure, retention, SLA deadlines (ADR-009/0005),
and the audit log of owned mutations. Does not own mail delivery, files, Flowable history, or
corporate credentials.

## Owned data

- `ticket` — the regulatory appeal card; UUIDv7 key plus a separate unique `registration_number`;
  optimistic-locking `version`; `contract_number` and `idempotency_key`.
- `ticket_applicant` — consumer and representative parties (by `applicant_type`); demographics
  nullable.
- `ticket_comment` — free-text comments attached to a ticket.
- `dictionary_entry` — business-configurable reference dictionaries keyed by
  `(dictionary_type, code)`.
- `registration_sequence` — per-year counter backing registration-number allocation.
- `outbox_event` — transactional outbox rows staged for publication.
- `audit_log` — append-only audit entries for owned mutations (no unmasked personal data).

## API

Base path `/api/v1`; camelCase; RFC 7807; `X-Correlation-ID`; optimistic locking via
`expectedVersion`; `Idempotency-Key` on create. Contract:
`contracts/openapi/ticket-service.v1.yaml`.

All ticket routes require a valid IAM-issued bearer token (verified independently, ADR-0008) plus the
listed permission claim and data-scope access; 401 without a valid token (with `WWW-Authenticate:
Bearer`), 403 without the permission or scope.

| Method | Path | Description | Required permission |
|---|---|---|---|
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (database connectivity) | none |
| POST | `/api/v1/tickets` | Register an appeal (idempotent) | `ticket:create` |
| GET | `/api/v1/tickets` | Search appeals (paginated, scoped) | `ticket:read` |
| GET | `/api/v1/tickets/{id}` | Get an appeal card | `ticket:read` |
| PATCH | `/api/v1/tickets/{id}` | Update card details | `ticket:update` |
| POST | `/api/v1/tickets/{id}/classify` | Set classification | `ticket:classify` |
| POST | `/api/v1/tickets/{id}/decision` | Record the decision | `ticket:decide` |
| POST | `/api/v1/tickets/{id}/close` | Close (validated); sets retention/terminal status | `ticket:close` |
| POST | `/api/v1/tickets/{id}/legal-hold` | Place or lift a legal hold | `ticket:legal_hold` |
| POST | `/api/v1/tickets/{id}/comments` | Add a comment | `ticket:comment` |
| GET | `/api/v1/tickets/{id}/comments` | List comments | `ticket:read` |

## Authentication and authorization

Independent JWT verification (`infrastructure/auth_tokens.py`) + permission gate
(`api/dependencies.require_permission`) + object/data scope (`domain/authorization.py`, fail-closed
EP-1 policy per ADR-0008). The actor for mutations/audit is the verified subject (`registered_by`,
`decision_by`, comment author) — never client input. No IAM code import or IAM DB access (ADR-004).

## Emitted events

Via the transactional outbox (`outbox_event`) and RabbitMQ relay:

- `ticket.created.v1` — an appeal is registered (identifier masked).
- `ticket.classified.v1` — classification set or changed.
- `ticket.updated.v1` — card details change (changed-field names only).
- `ticket.decision_recorded.v1` — a decision is recorded.
- `ticket.closed.v1` — an appeal is closed (with retention date).

Payload schemas: `contracts/events/payloads/`.

## Consumed events

None yet. Flowable projection events (`process.*`) are consumed from TASK_02D.

## External dependencies

- PostgreSQL — the compose stack; SQLite for local runs and unit tests.
- RabbitMQ — only when `TICKET_OUTBOX_RELAY_ENABLED=true` (disabled by default).

## Failure behavior

- `/health/ready` returns HTTP 503 when the database is unreachable.
- Not found → 404, version/integrity conflict → 409, invariant violation → 422 — all as RFC 7807
  Problem Details.
- Registration-number allocation serializes on the counter row; unique constraints are the backstop.
- Optimistic locking rejects concurrent card updates (`expectedVersion` mismatch → 409).
- The outbox guarantees an event is persisted iff its change commits; the relay retries unpublished
  events (at-least-once; consumers idempotent on `eventId`).

## Migrations

Alembic; latest revision `0004`.

- **migration:** `0001` core tables; `0003` comments, outbox, `contract_number`/`idempotency_key`,
  and search indexes; `0004` closure/SLA ticket columns and `audit_log`.
- **backfill:** `0002` seeds draft reference dictionaries (Q-A1).
- **rollback:** downgrades are destructive and guarded — dropping regulatory/audit tables or their
  columns aborts (`RegulatoryDataPresentError`) when protected tables hold rows (root `CLAUDE.md`,
  docs/01, docs/06); reference-data rollback (`downgrade 0001`) is unconditionally allowed.
- **validation:** `test_migration` (apply/seed/rollback, guard blocks downgrade on seeded data) and
  `test_models` (unique number, nullable demographics, optimistic locking).

## Testing

`python -m uv run pytest services/ticket_service` — health, registration number/allocator, pure and
persistence invariants, use cases (create/idempotency, update/classify/comment), search filters,
outbox relay, migrations, and HTTP API integration.

## Known limitations

- SQLite for local runs and unit tests; PostgreSQL in the compose stack.
- Draft dictionary codes pending the approved taxonomy (Q-A1).
- Case-insensitive name search relies on PostgreSQL `ILIKE` (SQLite folds ASCII only).
- The data-scope/confidentiality policy is a fail-closed EP-1 baseline (ADR-0008) pending the approved
  business matrix; the JWT scheme is dev/local symmetric (corporate OIDC/asymmetric is TASK_06).
- Wired into `docker-compose` (one-shot `ticket_migrate` + `ticket_service`, internal network only).
