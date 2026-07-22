# IAM Service

Identity and access for the MFO Appeals Platform: users, roles, teams, and the authorization
matrix. The service owns identity data and issues **permission claims** (a signed JWT) that
downstream services verify independently — there is no shared permission-rule library (ADR-007).

Authentication is a **temporary dev/local scheme available outside production only** (docs/06). In
production the dev login is disabled and the platform moves to corporate OIDC
(ADR-AUTH-OIDC, TASK_06). See [`docs/adr/ADR-0006-dev-auth-and-authorization.md`](../../docs/adr/ADR-0006-dev-auth-and-authorization.md).

## Roles and permissions

Seven roles (IAM_SERVICE spec): `EMPLOYEE`, `SUPERVISOR`, `FIRST_LINE_READONLY`, `OMBUDSMAN`,
`ANALYST`, `ADMIN`, `AUDITOR`. Each role maps to a set of `resource:action` permissions in
[`domain/permissions.py`](src/iam_service/domain/permissions.py). The regulatory invariant enforced
and tested is that `FIRST_LINE_READONLY` is read-only (docs/01): it grants only `ticket:read`.

## API

Base path `/api/v1`, JSON with camelCase fields, RFC 7807 Problem Details, `X-Correlation-ID`
propagation. Contract: [`contracts/openapi/iam-service.v1.yaml`](../../contracts/openapi/iam-service.v1.yaml).

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Dev/local login → signed access token | none (dev-only) |
| GET | `/api/v1/auth/me` | Current subject's claims | bearer token |
| POST | `/api/v1/users` | Create a user | `iam:manage` |
| GET | `/api/v1/users/{userId}` | Fetch a user | `iam:manage` |
| POST | `/api/v1/users/{userId}/roles` | Grant a role (idempotent) | `iam:manage` |
| DELETE | `/api/v1/users/{userId}/roles/{role}` | Revoke a role (idempotent) | `iam:manage` |
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (database) | none |

## Configuration

Environment variables use the `IAM_` prefix (see [`config.py`](src/iam_service/config.py)):

| Variable | Default | Purpose |
|---|---|---|
| `IAM_ENVIRONMENT` | `local` | Deployment environment. Dev login is available only for the closed allowlist `local`/`dev`/`test`; any other value (including `docker`, `staging`, `production`, or a misspelling) fails closed with dev auth OFF. |
| `IAM_DATABASE_URL` | SQLite file | Async SQLAlchemy URL (PostgreSQL in compose). |
| `IAM_DEV_AUTH_ENABLED` | `true` | Enables the dev login (effective only in an allowlisted environment). |
| `IAM_JWT_SECRET` | dev placeholder | Symmetric signing secret for dev tokens (never a real secret). The service refuses to start with the default or a secret shorter than 32 characters when dev auth is enabled outside `local`/`test`. |
| `IAM_JWT_ALGORITHM` | `HS256` | Dev token algorithm. |
| `IAM_JWT_ISSUER` | `mfo-iam` | Token `iss` claim. |
| `IAM_JWT_AUDIENCE` | `mfo-appeals` | Token `aud` claim. |
| `IAM_JWT_TTL_SECONDS` | `3600` | Token lifetime. |

## Owned data

`iam_team`, `iam_user`, `iam_user_role`, `iam_audit_log`. No cross-service database access
(ADR-004/007).

## Dev seed accounts (non-production only)

Migration `0002` seeds one user per role, all with the password `changeme-dev-01`. These accounts
exist for local development and demos only and must never be present in production.

| Username | Role |
|---|---|
| `employee` | EMPLOYEE |
| `supervisor` | SUPERVISOR |
| `firstline` | FIRST_LINE_READONLY |
| `ombudsman` | OMBUDSMAN |
| `analyst` | ANALYST |
| `admin` | ADMIN |
| `auditor` | AUDITOR |

## Local development

```bash
# Sync the workspace (all packages + dev deps) from the repo root.
python -m uv sync --all-packages --dev

# Apply migrations against the configured database.
cd services/iam_service && python -m uv run alembic upgrade head

# Run the service.
python -m uv run uvicorn iam_service.main:app --reload
```

## Testing

```bash
python -m uv run pytest services/iam_service contracts/tests/test_iam_openapi.py
```

Covers the authorization matrix (first-line read-only), password hashing, token issue/verify, dev
authentication, user/role administration with permission enforcement, audit writes, migration
apply/seed/rollback, and OpenAPI contract parity.

## Compose deployment

In `infrastructure/docker-compose.yml` a one-shot `iam_migrate` service runs `alembic upgrade head`
against PostgreSQL before `iam_service` starts (`service_completed_successfully` dependency), so API
containers never run migrations themselves and never serve an un-migrated schema. The service health
check uses schema-aware `/health/ready`, which fails until the core tables exist.

The PostgreSQL init script (`infrastructure/postgres/init/01-create-databases.sh`) creates the `iam`
role and `iam_service` database only on first cluster initialization. For a `pgdata` volume created
before this service existed, provision them once without deleting data:

```sql
CREATE USER iam WITH PASSWORD '<IAM_DB_PASSWORD>';
CREATE DATABASE iam_service OWNER iam;
```

## Known limitations

- Dev/local authentication only; corporate OIDC is TASK_06 (ADR-AUTH-OIDC).
- Downstream enforcement (Ticket Service verifying the issued claims) is not implemented here; it is
  TASK_01E-1 work and the platform authorization/IDOR risk (original CR-HIGH-001) stays open.
- SQLite for local runs and unit tests; PostgreSQL is exercised by `test_iam_migration_postgres.py`
  (run when `IAM_TEST_DATABASE_URL` is set) and the dedicated CI job.
- Non-compose local runs still apply migrations manually (`uv run alembic upgrade head`).
