# Event catalog

The single source of truth for event names on the MFO Appeals Platform. Every event is published
wrapped in the [event envelope](event-envelope.v1.json). Governed by ADR-006 and
[ADR-0004](../../docs/adr/ADR-0004-event-catalog.md).

## Naming

`<namespace>.<name>.v<version>` — for example, `ticket.created.v1`.

**Allowed namespaces:** `mail`, `ticket`, `response`, `process`, `document`, `notification`.
**Forbidden:** the `email.*` namespace and the ambiguous `response.returned` (ADR-006). The
envelope schema enforces the allowed namespaces via a pattern.

## Envelope

All events carry: `eventId`, `eventType`, `eventVersion`, `occurredAt`, `producer`,
`correlationId`, `causationId` (nullable), `payload`. Consumers are idempotent on `eventId`;
publishing uses the Transactional Outbox.

## Per-event documentation template

When a producing service introduces an event, document it with: **producer**, **consumers**,
**trigger**, **payload semantics**, **delivery guarantees**, **idempotency expectations**,
**versioning policy**, and **personal-data classification**. Payload field schemas are owned and
versioned by the producing service (added with that service).

## MVP events

Delivery guarantee for all: at-least-once via Transactional Outbox + RabbitMQ; consumers
idempotent on `eventId`. "PII" marks events whose payload may reference personal data (identifiers
are masked; full identifiers are never placed in payloads or logs).

### ticket.* — producer: ticket-service

| Event | Trigger | Consumers (initial) | PII |
|---|---|---|---|
| `ticket.created.v1` | A ticket is registered (manual or from mail) | process-adapter, notification | yes |
| `ticket.classified.v1` | A ticket is classified | process-adapter | no |
| `ticket.updated.v1` | Ticket details change | reporting read-model | yes |
| `ticket.decision_recorded.v1` | A decision is recorded | reporting read-model | no |
| `ticket.closed.v1` | A ticket is closed | reporting read-model, notification | no |
| `ticket.deadline_breached.v1` | An internal/regulatory deadline is breached | notification, reporting | no |
| `ticket.deadline_warning.v1` | A deadline is approaching (proposed) | notification | no |

**Implemented in TASK_01B** (payload schemas under [`payloads/`](payloads/); delivery at-least-once
via the transactional outbox; consumers idempotent on `eventId`; versioning per ADR-0004 — a
breaking payload change increments the `.vN` suffix):

- [`ticket.created.v1`](payloads/ticket.created.v1.json) — trigger: an appeal is registered.
  Payload: registry summary of the new ticket. **PII: yes** — the national identifier appears only
  masked (`identifierMasked`); the full identifier is never emitted.
- [`ticket.classified.v1`](payloads/ticket.classified.v1.json) — trigger: product/classifier/
  priority set or changed. Payload: the classification codes. PII: no.
- [`ticket.updated.v1`](payloads/ticket.updated.v1.json) — trigger: card details change. Payload:
  the list of changed field names only (values are not carried, to avoid leaking personal data);
  consumers re-read the card. **PII: yes** (changed-field names may reference personal-data fields).

**Implemented in TASK_01C** (same delivery/idempotency/versioning guarantees):

- [`ticket.decision_recorded.v1`](payloads/ticket.decision_recorded.v1.json) — trigger: a decision
  is recorded. Payload: decision code, timestamp, and author. PII: no.
- [`ticket.closed.v1`](payloads/ticket.closed.v1.json) — trigger: an appeal is closed. Payload:
  closure reason, closure timestamp, and retention date. PII: no.

### process.* — producer: process-adapter

| Event | Trigger | Consumers (initial) |
|---|---|---|
| `process.started.v1` | A Flowable process instance starts | ticket-service (projection) |
| `process.task_created.v1` | A user task is created | ticket-service, notification |
| `process.assignment_changed.v1` | A task assignment changes | ticket-service, notification |
| `process.status_changed.v1` | Process status/stage changes | ticket-service |
| `process.completed.v1` | A process instance completes | ticket-service |

### mail.* — producer: mailbox-service

| Event | Trigger | Consumers (initial) | PII |
|---|---|---|---|
| `mail.received.v1` | An inbound message is ingested | ticket-service | yes |
| `mail.linked.v1` | A reply is linked to a ticket | ticket-service, notification | yes |
| `mail.send_requested.v1` | An approved outbound send is requested | mailbox-service | yes |
| `mail.sent.v1` | An outbound message is sent | process-adapter, reporting | yes |
| `mail.send_failed.v1` | An outbound send fails | process-adapter, notification | yes |

### response.* — producer: ticket-service (lifecycle), process-adapter (authorization)

| Event | Trigger | Consumers (initial) |
|---|---|---|
| `response.draft_created.v1` | A response draft is created | process-adapter |
| `response.draft_approved.v1` | A response draft is approved | process-adapter |
| `response.send_authorized.v1` | Flowable authorizes sending | mailbox-service |

Introduced when the response lifecycle is implemented (EP-3/EP-5; ADR-008).

### document.* — producer: document-service

| Event | Trigger | Consumers (initial) |
|---|---|---|
| `document.uploaded.v1` | A document is uploaded | ticket-service |
| `document.available.v1` | A document passes scanning and is available | ticket-service, mailbox-service |
| `document.scan_failed.v1` | Antivirus marks a document infected/failed | ticket-service, notification |
| `document.deleted.v1` | A document is soft-deleted | ticket-service |

### notification.* — producer: notification-service

| Event | Trigger |
|---|---|
| `notification.requested.v1` | A notification is requested |
| `notification.delivered.v1` | A notification is delivered |
| `notification.failed.v1` | A notification fails |

## Future (post-MVP, AI)

Reserved and not emitted in MVP: `document.processing_requested.v1`, `document.ocr_completed.v1`,
`document.classified.v1`, `completeness.check_completed.v1`, `ai.run_completed.v1`. These are
introduced with the AI services (see `chatgpt_docs/docs/07_AI_READY_ARCHITECTURE.md`) and must be
added to the allowed namespaces at that time.
