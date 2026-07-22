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

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (database connectivity) | none |
| POST | `/api/v1/tickets` | Register an appeal (idempotent) | none (added in EP-1 IAM/BFF) |
| GET | `/api/v1/tickets` | Search appeals (paginated) | none |
| GET | `/api/v1/tickets/{id}` | Get an appeal card | none |
| PATCH | `/api/v1/tickets/{id}` | Update card details | none |
| POST | `/api/v1/tickets/{id}/classify` | Set classification | none |
| POST | `/api/v1/tickets/{id}/decision` | Record the decision | none |
| POST | `/api/v1/tickets/{id}/close` | Close (validated); sets retention/terminal status | none |
| POST | `/api/v1/tickets/{id}/legal-hold` | Place or lift a legal hold | none |
| POST | `/api/v1/tickets/{id}/comments` | Add a comment | none |
| GET | `/api/v1/tickets/{id}/comments` | List comments | none |

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
- **rollback:** `downgrade base` drops the schema; `downgrade 0001` removes only seed rows; no
  regulatory data is deleted.
- **validation:** `test_migration` (apply/seed/rollback incl. `ticket_comment`/`outbox_event`/
  `audit_log`) and `test_models` (unique number, nullable demographics, optimistic locking).

## Testing

`python -m uv run pytest services/ticket_service` — health, registration number/allocator, pure and
persistence invariants, use cases (create/idempotency, update/classify/comment), search filters,
outbox relay, migrations, and HTTP API integration.

## Known limitations

- SQLite for local runs and unit tests; PostgreSQL in the compose stack.
- Draft dictionary codes pending the approved taxonomy (Q-A1).
- Case-insensitive name search relies on PostgreSQL `ILIKE` (SQLite folds ASCII only).
- No authentication yet (TASK_01D/01E); not wired into `docker-compose`.
