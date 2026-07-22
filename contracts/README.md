# contracts

Versioned OpenAPI and JSON Schema contracts, validated in CI. Change contracts before
implementation (contract-first).

## Contents

- [`events/event-envelope.v1.json`](events/event-envelope.v1.json) — the common event envelope
  (JSON Schema, Draft 2020-12).
- [`events/CATALOG.md`](events/CATALOG.md) — the canonical event catalog: allowed namespaces,
  the MVP event list, and the per-event documentation template (ADR-006 / ADR-0004).
- [`openapi/ticket-service.v1.yaml`](openapi/ticket-service.v1.yaml) — the Ticket Service REST API
  (OpenAPI 3.1).
- [`events/payloads/`](events/payloads/) — per-event payload schemas owned by the producing
  service (currently `ticket.created/classified/updated.v1`).
- `tests/` — contract tests: envelope validity, ticket payload validity and envelope conformance,
  and OpenAPI 3.1 validation.

Per-service OpenAPI specs and per-event payload schemas are added as their services are
implemented.
