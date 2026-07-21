# SERVICE_MAP — ticket-service

Structured map of the ticket service. Kept current as behavior changes (Definition of Done, root
`CLAUDE.md`).

## Responsibility

Regulatory registry and appeal card: the ticket model, applicants/representatives, reference
dictionaries, decision, closure, and retention. Does not own mail delivery, files, Flowable
history, or corporate credentials.

## Owned data

- `ticket` — the regulatory appeal card; internal UUIDv7 key plus a separate unique
  `registration_number`; optimistic-locking `version`.
- `ticket_applicant` — consumer and representative parties (distinguished by `applicant_type`);
  demographics nullable.
- `dictionary_entry` — business-configurable reference dictionaries keyed by
  `(dictionary_type, code)`.
- `registration_sequence` — per-year counter backing registration-number allocation.

## API

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (database connectivity) | none |

Business endpoints (create/update/classify/comment/search) are added in TASK_01B+.

## Emitted events

None yet. `ticket.created.v1`, `ticket.classified.v1`, `ticket.updated.v1` (via the Transactional
Outbox) arrive in TASK_01B.

## Consumed events

None yet. Flowable projection events (`process.*`) are consumed from TASK_02D.

## External dependencies

- PostgreSQL — used in the compose stack (`postgresql+asyncpg://…`); SQLite for local (non-Docker)
  runs and unit tests.

## Failure behavior

- `/health/ready` returns HTTP 503 with a per-check report when the database is unreachable.
- Registration-number allocation serializes on the counter row; the unique constraint on
  `ticket.registration_number` is the backstop against duplicates.
- Concurrent ticket updates are rejected via optimistic locking (`StaleDataError`).

## Migrations

Alembic; latest revision `0002`.

- **migration:** `0001_create_ticket_tables` creates `ticket`, `ticket_applicant`,
  `dictionary_entry`, `registration_sequence`.
- **backfill:** `0002_seed_dictionaries` seeds draft reference dictionaries (Q-A1).
- **rollback:** `alembic downgrade base` drops the schema; `downgrade 0001` removes only seed rows;
  no regulatory data is deleted.
- **validation:** `test_migration` (apply/seed/rollback) and `test_models` (unique number, nullable
  demographics, optimistic locking).

## Testing

`uv run pytest services/ticket_service` — health, registration number/allocator, pure invariants,
persistence invariants, and migration apply/rollback tests.

## Known limitations

- SQLite for local runs and unit tests; PostgreSQL in the compose stack.
- Draft dictionary codes pending the approved taxonomy (Q-A1).
- National identifier stored but not yet masked in outputs (Q-D3); no business API/search/events
  yet (TASK_01B+).
