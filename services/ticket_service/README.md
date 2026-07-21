# ticket-service

Regulatory registry and appeal card for the MFO Appeals Platform. It owns the ticket model, the
parties attached to an appeal (consumer and representative), the business-configurable reference
dictionaries, and the business **registration number**.

**Scope of TASK_01A (this increment):** data model, migrations, and registration-number
allocation. Use cases (create/update/classify/comment), search, events, and business HTTP
endpoints arrive in TASK_01B+; only health endpoints are exposed here.

## What it provides today

- The `domain` / `application` / `infrastructure` / `api` layering (copied from the service
  template).
- SQLAlchemy models: `ticket`, `ticket_applicant`, `dictionary_entry`, `registration_sequence`.
- A `RegistrationNumber` value object (`AP-YYYY-NNNNNN`) and a counter-backed
  `RegistrationNumberAllocator` that issues unique, per-year numbers.
- Pure lifecycle invariants (required registration fields; closure prerequisites; five-year
  retention) ready for the TASK_01C use cases.
- Alembic migrations: schema (`0001`) and draft reference dictionaries (`0002`, Q-A1).
- Health endpoints: `GET /health/live` and `GET /health/ready` (database connectivity).

## Data ownership

Per the platform data-ownership rules (root `CLAUDE.md`): the ticket card, applicants,
classification codes, decision, closure, and retention. It does **not** own mail delivery, files,
Flowable history, or corporate credentials. Status and stage are Flowable projections in later
phases; at registration they hold their initial values.

## Local development

```bash
uv run uvicorn ticket_service.main:app --reload   # run the service (SQLite)
uv run pytest services/ticket_service             # run its tests
cd services/ticket_service && uv run alembic upgrade head   # apply migrations (SQLite)
```

For local (non-Docker) runs and unit tests the service uses an embedded SQLite backend
(`TICKET_DATABASE_URL=sqlite+aiosqlite:///./ticket_service.db`).

## Configuration

Environment variables (prefix `TICKET_`):

| Variable | Default | Description |
|---|---|---|
| `TICKET_ENVIRONMENT` | `local` | Deployment environment name. |
| `TICKET_DATABASE_URL` | `sqlite+aiosqlite:///./ticket_service.db` | SQLAlchemy async database URL. |
| `TICKET_REGISTRATION_NUMBER_PREFIX` | `AP` | Prefix embedded in registration numbers. |

## Registration number

The registration number is the human-facing appeal identifier, kept separate from the internal
UUIDv7 surrogate key (ADR-003). Format: `{PREFIX}-{YEAR}-{SEQUENCE}` with a zero-padded, per-year
monotonic sequence (for example `AP-2026-000001`). Uniqueness is guaranteed by locking the
`registration_sequence` counter row on allocation and by a unique constraint on
`ticket.registration_number`.

## Migrations

- **migration:** `0001_create_ticket_tables` creates the four tables.
- **backfill:** `0002_seed_dictionaries` seeds draft channel/product/classifier/priority/status/
  stage/decision/closure-reason/gender dictionaries (Q-A1; codes are mapped later, not discarded).
- **rollback:** `alembic downgrade base` drops the schema; `downgrade 0001` removes only the seed
  rows. No regulatory appeal data is deleted (root `CLAUDE.md`).
- **validation:** `test_migration` applies/seeds/reverts against SQLite; `test_models` covers the
  unique registration number, nullable demographics, and optimistic locking.

## Known limitations

- SQLite is used for local (non-Docker) runs and unit tests; the compose stack uses PostgreSQL.
- Reference dictionaries hold draft codes pending the approved business taxonomy (Q-A1).
- No business API, search, or events yet (TASK_01B+); the national identifier is stored but not
  yet masked in outputs (Q-D3).
