# ADR-0004: Event catalog and envelope

- **Status:** Accepted
- **Related:** DECISION_LOG ADR-006

## Context

Three source documents named the same events differently (`email.*` vs `mail.*`; `deadline.*` vs
`ticket.deadline_breached.v1`), and the notification service consumed events absent from the
catalog. Without a single source of truth, producers and consumers drift and contract tests cannot
be meaningful.

## Decision

- Maintain a single canonical event catalog: [`contracts/events/CATALOG.md`](../../contracts/events/CATALOG.md).
- All events are wrapped in the versioned envelope
  [`contracts/events/event-envelope.v1.json`](../../contracts/events/event-envelope.v1.json) with
  fields `eventId`, `eventType`, `eventVersion`, `occurredAt`, `producer`, `correlationId`,
  `causationId` (nullable), `payload`.
- `eventType` is `<namespace>.<name>.v<version>`. Allowed namespaces: `mail`, `ticket`,
  `response`, `process`, `document`, `notification`. The `email.*` namespace and `response.returned`
  are forbidden (ADR-006). The envelope schema enforces the allowed namespaces via a pattern.
- Payload schemas are owned and versioned by the producing service and added with that service.
  Each event is documented with producer, consumers, trigger, payload semantics, delivery
  guarantees, idempotency expectations, versioning policy, and personal-data classification.
- Delivery is at-least-once via the Transactional Outbox and RabbitMQ; consumers are idempotent on
  `eventId`.
- Versioning: a breaking payload change increments the version suffix (`.v2`) and `eventVersion`;
  the old version remains until consumers migrate.

## Alternatives considered

- **Keep per-document naming:** rejected — the ambiguity that motivated this ADR.
- **Version only via `eventVersion`, unversioned `eventType`:** rejected — the source catalog uses
  versioned names; keeping the suffix makes routing and topic naming explicit.
- **A shared events library with concrete payload models:** rejected — payloads belong to owning
  services (ADR-007); only the envelope schema and catalog are shared.

## Consequences

- The envelope schema is validated by contract tests (`contracts/tests/`), and CI runs them.
- New events must be added to the catalog and use an allowed namespace; forbidden namespaces fail
  schema validation.
- Future AI events (for example, `document.ocr_completed.v1`) require adding their namespaces to
  the allowed set when those services are introduced.

## Migration impact

The Ticket Service is the first producer (EP-1): it emits `ticket.created.v1`,
`ticket.classified.v1`, `ticket.updated.v1`, `ticket.decision_recorded.v1`, and `ticket.closed.v1`
through the transactional outbox, with payload schemas under `contracts/events/payloads/`. Further
producers adopt the same envelope and catalog from their first event.

## Rollback considerations

The catalog and envelope are additive contracts; a superseding ADR can change the envelope by
introducing `event-envelope.v2.json` without breaking existing v1 producers.
