# SERVICE_MAP — iam-service

Structured map of the IAM service. Kept current as behavior changes (Definition of Done, root
`CLAUDE.md`).

## Responsibility

Owns identity: users, roles, teams, and the authorization matrix. Issues permission claims (signed
JWT) consumed by other services, which enforce authorization independently (ADR-007). Provides
dev/local authentication outside production only (docs/06).

## Owned data

- `iam_team` — organizational teams.
- `iam_user` — user accounts with bcrypt password hashes (dev/local auth) and optimistic-locking
  `version`.
- `iam_user_role` — per-user role grants (unique per `(user_id, role)`).
- `iam_audit_log` — security-relevant identity actions (login, user creation, role changes).

## API

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Dev/local login → access token | none (dev-only) |
| GET | `/api/v1/auth/me` | Current subject's claims | bearer token |
| POST | `/api/v1/users` | Create a user | `iam:manage` |
| GET | `/api/v1/users/{userId}` | Fetch a user | `iam:manage` |
| POST | `/api/v1/users/{userId}/roles` | Grant a role | `iam:manage` |
| DELETE | `/api/v1/users/{userId}/roles/{role}` | Revoke a role | `iam:manage` |
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (database connectivity) | none |

## Authorization matrix

Role → permission mapping in `domain/permissions.py`. `FIRST_LINE_READONLY` is read-only
(`ticket:read` only); `AUDITOR` is read-only across appeals, reports, and audit; `ADMIN` holds
`iam:manage` only. Downstream services check the resolved permission strings carried by the token.

## Emitted events

None. The `iam.*` namespace is not part of the event catalog (ADR-006); identity changes are audited
internally rather than published.

## Consumed events

None.

## External dependencies

- PostgreSQL — used in the compose stack (`postgresql+asyncpg://…`); SQLite for local (non-Docker)
  runs and unit tests.

## Failure behavior

- `/health/ready` returns HTTP 503 with a per-check report when the database is unreachable or the
  IAM schema is not migrated (schema-aware readiness).
- Invalid credentials → 401; malformed/expired/unknown-role token → 401; dev login disabled
  (non-allowlisted environment) → 403; missing permission → 403; unknown user/role → 404; duplicate
  username → 409; invalid input → 422 (RFC 7807).
- Startup fails closed (`InsecureDevAuthConfigError`) when dev auth is enabled outside `local`/`test`
  with the default or a too-short signing secret.

## Migrations

Alembic; apply with `cd services/iam_service && uv run alembic upgrade head`.

- **migration:** `0001_create_iam_tables` creates the identity and audit schema.
- **backfill/seed:** `0002_seed_roles_and_dev_users` inserts teams, one dev user per role, and role
  grants (immutable snapshot; adding roles/users later is a new migration).
- **rollback:** `alembic downgrade base`. The `0001` downgrade refuses to drop non-empty identity or
  audit data (`migration_guards.abort_if_tables_not_empty`); `0002` deletes only the seeded rows by
  primary key.
- **validation:** `test_iam_migration` (SQLite) applies, checks the seed and seeded-hash
  verification, reverts, and asserts the protection guard trips; `test_iam_migration_postgres`
  exercises the full lifecycle on real PostgreSQL (enum-typed seed, guarded downgrade, enum cleanup,
  re-upgrade) when `IAM_TEST_DATABASE_URL` is set, plus a dedicated CI job.
- **compose:** a one-shot `iam_migrate` service runs `alembic upgrade head` before `iam_service`
  starts, so API replicas never migrate and never serve an un-migrated schema.

## Testing

`uv run pytest services/iam_service` plus `contracts/tests/test_iam_openapi.py`. PostgreSQL migration
tests run when `IAM_TEST_DATABASE_URL` points at a database.

## Known limitations

- Dev/local authentication only; corporate OIDC is TASK_06 (ADR-AUTH-OIDC).
- Downstream claim enforcement (Ticket Service) is TASK_01E-1; the platform authorization/IDOR risk
  (original CR-HIGH-001) remains open.
- SQLite for local runs and unit tests; PostgreSQL exercised by the migration test/CI job and the
  compose stack.
