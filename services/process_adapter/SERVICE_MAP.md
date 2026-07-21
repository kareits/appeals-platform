# SERVICE_MAP — process-adapter

Structured map of the Process Adapter service. Kept current as behavior changes (Definition of
Done, root `CLAUDE.md`).

## Responsibility

Domain adapter over Flowable. In TASK_00D it is a technical spike validating the integration loop;
the domain commands, projection events, and own database are added in EP-3 (TASK_02).

## Owned data

None yet (the spike has no own database).

## API

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health/live` | Liveness probe | none |
| GET | `/health/ready` | Readiness probe (Flowable reachability) | none |

## Emitted events

None yet (projection events are introduced in EP-3).

## Consumed events

None yet.

## External dependencies

- Flowable REST API (`/flowable-rest/service`), basic auth. Reached on the internal network.

## Failure behavior

- `/health/ready` returns HTTP 503 when the Flowable REST API is unreachable.

## Migrations

None (no own database in this phase).

## Testing

- Unit run (default): integration tests are skipped unless `PA_FLOWABLE_BASE_URL` is set.
- Integration: `make spike` publishes Flowable and runs `services/process_adapter` tests, covering
  the full loop and idempotent start.

## Known limitations

- Spike only: no domain commands, projection events, authorization, or persistence yet.
- Idempotency is enforced by querying Flowable by business key before starting (Flowable does not
  enforce business-key uniqueness).
