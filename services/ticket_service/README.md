# ticket-service

Regulatory registry and appeal card for the MFO Appeals Platform. It owns the ticket model, the
parties attached to an appeal (consumer and representative), the business-configurable reference
dictionaries, the business **registration number**, comments, and the appeal lifecycle use cases
(manual registration, update, classification, comments, search).

**Scope through TASK_01C (this increment):** the data model and registration number (TASK_01A);
use cases, search, and `ticket.*` events (TASK_01B); and decision, close validation, retention, SLA
deadlines, the audit log, and legal hold (TASK_01C). Authentication is provided later by IAM/BFF
(TASK_01D/01E).

## What it provides

- The `domain` / `application` / `infrastructure` / `api` layering.
- SQLAlchemy models: `ticket`, `ticket_applicant`, `dictionary_entry`, `registration_sequence`,
  `ticket_comment`, `outbox_event`, `audit_log`.
- Use cases: `create_manual_ticket`, `update_ticket_details`, `classify_ticket`, `record_decision`,
  `close_ticket`, `set_legal_hold`, `add_comment`, `list_comments`, `search_tickets` (business logic
  lives in the application layer, not routes).
- SLA deadlines computed at registration from a versioned policy and a business calendar
  (`internal_due_at`/`legal_due_at`, ADR-0005); close validation, five-year retention, and an audit
  log of mutations.
- A `RegistrationNumber` value object (`AP-YYYY-NNNNNN`) and a counter-backed allocator issuing
  unique, per-year numbers.
- Pure lifecycle invariants (required registration fields; closure prerequisites; five-year
  retention) — the closure/retention ones are wired up in TASK_01C.
- A transactional outbox emitting `ticket.created.v1`, `ticket.classified.v1`, `ticket.updated.v1`,
  with a background relay that publishes to RabbitMQ (opt-in, see configuration).
- REST API under `/api/v1` and health endpoints (`/health/live`, `/health/ready`).

## API

Base path `/api/v1`; JSON camelCase; RFC 7807 errors; `X-Correlation-ID`; optimistic locking via
`expectedVersion`; `Idempotency-Key` on create. Contract:
[`contracts/openapi/ticket-service.v1.yaml`](../../contracts/openapi/ticket-service.v1.yaml).

| Method | Path | Description |
|---|---|---|
| POST | `/tickets` | Register an appeal (idempotent with `Idempotency-Key`). |
| GET | `/tickets` | Search by number/IIN-BIN/name/contract/status/stage/product/classifier/channel/assignee/team/dates; paginated. |
| GET | `/tickets/{id}` | Get the appeal card. |
| PATCH | `/tickets/{id}` | Update card details (not status/stage/assignment). |
| POST | `/tickets/{id}/classify` | Set product/classifier/priority. |
| POST | `/tickets/{id}/decision` | Record the decision. |
| POST | `/tickets/{id}/close` | Close after validating prerequisites; sets retention and terminal status. |
| POST | `/tickets/{id}/legal-hold` | Place or lift a legal hold. |
| POST/GET | `/tickets/{id}/comments` | Add/list comments. |

Status, stage, and assignment are Flowable projections and are **not** editable through this API
(they change only via the projection mechanism; a placeholder in EP-1).

## Events (transactional outbox)

Emitted via `outbox_event` (staged in the same transaction as the change) and relayed to RabbitMQ:

| Event | Trigger | PII |
|---|---|---|
| `ticket.created.v1` | An appeal is registered | yes (identifier masked) |
| `ticket.classified.v1` | Classification set/changed | no |
| `ticket.updated.v1` | Card details change (carries changed-field names only) | yes |
| `ticket.decision_recorded.v1` | A decision is recorded | no |
| `ticket.closed.v1` | An appeal is closed | no |

Payload schemas: [`contracts/events/payloads/`](../../contracts/events/payloads/). Full national
identifiers never appear in events or logs — only a masked form (docs/06, Q-D3).

## Data ownership

The ticket card, applicants, classification codes, comments, decision, closure, and retention. It
does **not** own mail delivery, files, Flowable history, or corporate credentials.

## Local development

```bash
python -m uv run uvicorn ticket_service.main:app --reload      # run the service (SQLite)
python -m uv run pytest services/ticket_service                # run its tests
cd services/ticket_service && python -m uv run alembic upgrade head   # apply migrations (SQLite)
```

For local (non-Docker) runs and unit tests the service uses an embedded SQLite backend. The outbox
relay is disabled by default, so no broker is needed locally.

## Configuration

Environment variables (prefix `TICKET_`):

| Variable | Default | Description |
|---|---|---|
| `TICKET_ENVIRONMENT` | `local` | Deployment environment name. |
| `TICKET_DATABASE_URL` | `sqlite+aiosqlite:///./ticket_service.db` | SQLAlchemy async database URL. |
| `TICKET_REGISTRATION_NUMBER_PREFIX` | `AP` | Prefix embedded in registration numbers. |
| `TICKET_OUTBOX_RELAY_ENABLED` | `false` | Run the background relay that publishes staged events to RabbitMQ. |
| `TICKET_RABBITMQ_URL` | `amqp://guest:guest@localhost/` | AMQP URL used by the relay when enabled. |
| `TICKET_RABBITMQ_EXCHANGE` | `appeals.events` | Topic exchange the relay publishes to. |
| `TICKET_OUTBOX_RELAY_INTERVAL_SECONDS` | `2.0` | Delay between relay passes. |
| `PLATFORM_TIMEZONE` | `Asia/Almaty` | Platform-wide business timezone for date/working-hours math (shared; storage stays UTC). Also readable as `TICKET_PLATFORM_TIMEZONE`. |

## Time and SLA

Timestamps are stored in UTC (ADR-003). Business dates and working-hours computation use the
platform business timezone (Kazakhstan/Almaty, UTC+5) via `PLATFORM_TIMEZONE`; the retention date is
computed from the closure instant in that timezone. SLA deadlines use a versioned policy
(`v1-temp`: resolution 24h, regulatory term 15 calendar days) and a temporary 24/7 calendar, both
behind interfaces for a later KZ working-hours/holiday calendar (ADR-0005, Q-C1).

## Registration number

The registration number is the human-facing appeal identifier, kept separate from the internal
UUIDv7 surrogate key (ADR-003). Format: `{PREFIX}-{YEAR}-{SEQUENCE}` with a zero-padded, per-year
monotonic sequence (for example `AP-2026-000001`). Uniqueness is guaranteed by locking the
`registration_sequence` counter row on allocation and by a unique constraint on
`ticket.registration_number`.

## Migrations

- **migration:** `0001` creates the core tables; `0003` adds `ticket_comment`, `outbox_event`, the
  `contract_number`/`idempotency_key` ticket columns, and the search indexes; `0004` adds the
  `sla_policy_version`/`response_sent_at`/`no_response_reason` ticket columns and `audit_log`.
- **backfill:** `0002` seeds draft reference dictionaries (Q-A1; codes are mapped later, not
  discarded).
- **rollback:** downgrades are **destructive and guarded** — dropping regulatory/audit tables
  (`ticket`, `ticket_applicant`, `ticket_comment`, `outbox_event`, `audit_log`) or their columns
  aborts with `RegulatoryDataPresentError` if any hold rows (root `CLAUDE.md`, docs/01, docs/06); use
  a forward-fix migration or an explicit audited purge instead. Only reference-data rollback
  (`downgrade 0001` removing seed dictionaries) is unconditionally allowed. On an empty schema a full
  `downgrade base` is permitted.
- **validation:** `test_migration` applies/seeds/reverts against SQLite; `test_models` covers the
  unique registration number, nullable demographics, and optimistic locking.

## Known limitations

- SQLite for local (non-Docker) runs and unit tests; the compose stack uses PostgreSQL.
- Reference dictionaries hold draft codes pending the approved business taxonomy (Q-A1).
- Case-insensitive name search relies on the PostgreSQL `ILIKE` collation; SQLite folds ASCII only.
- No authentication yet (TASK_01D/01E); actor identifiers are supplied by the caller.
- Not yet wired into `docker-compose`.
