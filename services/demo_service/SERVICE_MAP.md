# SERVICE_MAP — demo-service

Structured map of the demo service. Real services keep this file current as behavior changes
(Definition of Done, root `CLAUDE.md`).

## Responsibility

Reference bootstrap service. No business responsibility; demonstrates platform wiring and serves
as a service template.

## Owned data

- `bootstrap_marker` table (a trivial marker used to validate migrations and persistence).

## API

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (database connectivity) | none |

## Emitted events

None (event publishing is introduced in later phases).

## Consumed events

None.

## External dependencies

- PostgreSQL — used in the compose stack (`postgresql+asyncpg://…`); SQLite for local (non-Docker)
  runs and unit tests.

## Failure behavior

- `/health/ready` returns HTTP 503 with a per-check report when the database is unreachable.

## Migrations

Alembic; latest revision `0001` creates `bootstrap_marker`. Apply with
`cd services/demo_service && uv run alembic upgrade head`.

- **migration:** `0001_create_bootstrap_marker` creates the table.
- **backfill:** none.
- **rollback:** `alembic downgrade base` drops the table.
- **validation:** `test_sample_migration` applies then reverts the migration against SQLite.

## Testing

`uv run pytest services/demo_service` — health endpoint tests and the migration apply/rollback test.

## Known limitations

- SQLite is used for local (non-Docker) runs and unit tests; the compose stack uses PostgreSQL.
- No authentication or business logic (out of scope for the bootstrap).
