# 05. API и события

## API conventions

- `/api/v1`;
- JSON camelCase;
- ISO-8601 UTC;
- RFC 7807 Problem Details;
- `X-Correlation-ID`;
- единая pagination;
- optimistic locking;
- `Idempotency-Key` для команд.

## BFF endpoints

- `GET /workspace/my`
- `GET/POST /tickets`
- `GET /tickets/{id}/workspace`
- `PATCH /tickets/{id}`
- `POST /tickets/{id}/comments`
- `POST /tickets/{id}/documents`
- `POST /tickets/{id}/tasks/{taskId}/complete`
- `POST /tickets/{id}/reassign`
- `POST /tickets/{id}/responses`
- `POST /tickets/{id}/responses/{responseId}/approve`
- `POST /tickets/{id}/responses/{responseId}/send`
- `GET /reports/...`

## Event envelope

```json
{
  "eventId": "uuid",
  "eventType": "ticket.created",
  "eventVersion": 1,
  "occurredAt": "2026-01-01T00:00:00Z",
  "producer": "ticket-service",
  "correlationId": "uuid",
  "causationId": "uuid",
  "payload": {}
}
```

## MVP events

Ticket:
- ticket.created.v1
- ticket.classified.v1
- ticket.updated.v1
- ticket.decision_recorded.v1
- ticket.closed.v1
- ticket.deadline_breached.v1

Process:
- process.started.v1
- process.task_created.v1
- process.assignment_changed.v1
- process.status_changed.v1
- process.completed.v1

Mail:
- mail.received.v1
- mail.linked.v1
- mail.send_requested.v1
- mail.sent.v1
- mail.send_failed.v1

Document:
- document.uploaded.v1
- document.available.v1
- document.scan_failed.v1
- document.deleted.v1

Notification:
- notification.requested.v1
- notification.delivered.v1
- notification.failed.v1

Future AI:
- document.processing_requested.v1
- document.ocr_completed.v1
- document.classified.v1
- completeness.check_completed.v1
- response.draft_created.v1
- response.draft_approved.v1
- ai.run_completed.v1

## Contract tests

OpenAPI validation, event schema validation, consumer tests, compatibility checks, duplicate delivery and unavailable dependency.
