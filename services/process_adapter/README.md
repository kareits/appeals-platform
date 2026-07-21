# process-adapter

Domain adapter over the Flowable REST API. It isolates the rest of the platform from
Flowable-specific endpoints and payloads.

> **Status: technical spike (TASK_00D).** This phase validates the integration loop and has no own
> database, no projection events, and no domain commands. EP-3 (TASK_02) builds the real adapter
> on this foundation.

## What the spike validates

The full Process Adapter ↔ Flowable loop, exercised by the integration tests against a running
Flowable:

1. deploy a BPMN process;
2. **idempotent start** by business key (starting twice reuses the same instance);
3. user task: **claim** and **complete**;
4. **timer** intermediate event fires (short `PT2S` duration);
5. **message** correlation (deliver a message to the waiting execution);
6. read **history** (activities and completion).

The technical pattern (endpoints, actions, polling) lives in
`src/process_adapter/infrastructure/flowable_client.py` and `application/spike.py` and is the
reference for EP-3.

## Layout

- `infrastructure/flowable_client.py` — async Flowable REST client (basic auth, timeout).
- `application/spike.py` — high-level spike operations (idempotent start, full cycle).
- `application/health.py`, `api/health.py` — `/health/live` and `/health/ready` (checks Flowable).
- `tests/resources/spike_process.bpmn20.xml` — the technical spike BPMN (no business meaning).

## Configuration

Environment variables (prefix `PA_`):

| Variable | Default | Description |
|---|---|---|
| `PA_ENVIRONMENT` | `local` | Deployment environment name. |
| `PA_FLOWABLE_BASE_URL` | `http://flowable:8080/flowable-rest/service` | Flowable REST base URL. |
| `PA_FLOWABLE_USERNAME` | `rest-admin` | Flowable REST basic-auth user. |
| `PA_FLOWABLE_PASSWORD` | `test` | Flowable REST basic-auth password. |

## Running the integration tests

Flowable is internal-only in the base compose file, so the integration tests are skipped unless
`PA_FLOWABLE_BASE_URL` is set. A local override publishes Flowable for the spike:

```bash
make spike        # publishes Flowable on :8081 and runs services/process_adapter tests
make spike-down   # stops the spike stack
```

Under the default `uv run pytest` (and the CI quality job) these tests are skipped.

## Notes for EP-3

Flowable REST facts confirmed by the spike: base path `/flowable-rest/service`; default credentials
`rest-admin`/`test`; task actions via `POST /runtime/tasks/{id}` (`claim`, `complete`); message
correlation via `PUT /runtime/executions/{id}` with `messageEventReceived`; timers require the
async job executor (enabled by default). Idempotency is enforced by the adapter (query by business
key before starting), not by Flowable.
