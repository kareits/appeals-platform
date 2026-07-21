# infrastructure

Local development stack (TASK_00B, EP-0) defined in [`docker-compose.yml`](docker-compose.yml).

## Services

| Service | Image | Host port | Notes |
|---|---|---|---|
| `postgres` | postgres:16 | none | Shared cluster; separate DB + user per service (ADR-004). |
| `rabbitmq` | rabbitmq:3.13-management | 15672 (management UI, dev) | AMQP stays internal. |
| `flowable` | flowable/flowable-rest:7.1.0 | none | Own database; reachable only on the internal network. |
| `demo_service` | built from `services/demo_service/Dockerfile` | none | Reached only via the reverse proxy. |
| `reverse-proxy` | caddy:2.8 | `HTTP_PORT` (default 8080) → 80 | The only service that publishes a host port. |

Databases created on first init (see `postgres/init/01-create-databases.sh`): `demo_service`
(owner `demo`) and `flowable` (owner `flowable`).

## Run

```bash
make up          # build and start everything in the background
make ps          # service status
make migrate     # apply demo-service migrations against the compose PostgreSQL
make logs        # follow logs
make down        # stop and remove containers
```

Then check the demo service through the proxy:

```bash
curl http://localhost:8080/health/live     # {"status":"alive"}
curl http://localhost:8080/health/ready    # {"status":"healthy","checks":{"database":"healthy"}}
```

## Configuration

Credentials are non-secret dev placeholders with inline defaults, so `make up` works without an
`.env` file. Override via `.env` (see `.env.example`). Never commit real secrets.

- **Port conflicts:** if the default host port 8080 is taken, set `HTTP_PORT` (for example,
  `HTTP_PORT=8090 make up`, or put `HTTP_PORT=8090` in `.env`).
- **Windows / Git Bash:** the `migrate` target uses an absolute container working directory
  (`-w /app/...`). Git Bash rewrites such paths (MSYS path conversion); prefix the command with
  `MSYS_NO_PATHCONV=1` when running it directly in Git Bash. Under `make` on Linux/CI this is not
  needed.

## Boundaries (verified)

- Flowable and PostgreSQL publish no host ports; only the reverse proxy and the RabbitMQ
  management UI are reachable from the host.
- The demo service connects to PostgreSQL (`postgresql+asyncpg://…`) in compose; local unit tests
  still use SQLite.

## Out of scope (later phases)

CI and the event-envelope schema (TASK_00C); production config, secrets, TLS, and backup/restore
(EP-7). PostgreSQL is used for Flowable persistence; deep Flowable integration is validated in the
Flowable spike (TASK_00D) and EP-3.
