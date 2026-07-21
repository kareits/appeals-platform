# IAM Service

## Назначение
Пользователи, роли, команды и корпоративный IdP.

## MVP
Dev/local auth только вне production, users, roles, teams, permission claims.

## Future
OIDC with corporate AD/Entra, group sync.

## Roles
EMPLOYEE, SUPERVISOR, FIRST_LINE_READONLY, OMBUDSMAN, ANALYST, ADMIN, AUDITOR.

## Security
No shared accounts, proper password hashing for temporary auth, production disables dev login, role changes audited.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
