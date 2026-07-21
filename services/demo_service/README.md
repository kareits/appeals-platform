# demo-service

Demonstration service and **reference template** for MFO Appeals Platform services. It has no
business domain; it exists to prove the bootstrap wiring and to be copied when scaffolding a real
service.

## What it demonstrates

- The `domain` / `application` / `infrastructure` / `api` layering.
- Reuse of the shared libraries (`mfo-observability`, `mfo-http`).
- Structured logging, correlation-ID middleware, and RFC 7807 error handling.
- Health endpoints: `GET /health/live` and `GET /health/ready` (checks database connectivity).
- Async SQLAlchemy 2 persistence and an Alembic migration.

## Local development

```bash
uv run uvicorn demo_service.main:app --reload   # run the service
uv run pytest services/demo_service             # run its tests
cd services/demo_service && uv run alembic upgrade head   # apply migrations
```

For local runs and tests the service uses an embedded SQLite backend
(`DEMO_DATABASE_URL=sqlite+aiosqlite:///./demo_service.db`). PostgreSQL wiring arrives in TASK_00B.

## Configuration

Environment variables (prefix `DEMO_`):

| Variable | Default | Description |
|---|---|---|
| `DEMO_ENVIRONMENT` | `local` | Deployment environment name. |
| `DEMO_DATABASE_URL` | `sqlite+aiosqlite:///./demo_service.db` | SQLAlchemy async database URL. |

## Creating a new service from this template

Copy `services/demo_service`, rename the `demo_service` package and the distribution name in
`pyproject.toml`, add the new member to the root `pyproject.toml` workspace, then replace the demo
model, health checks, and routes with the real service's domain. Follow the Definition of Done in
the root `CLAUDE.md`.
