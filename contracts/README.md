# contracts

Versioned OpenAPI and JSON Schema contracts, validated in CI. Change contracts before
implementation (contract-first).

## Contents

- [`events/event-envelope.v1.json`](events/event-envelope.v1.json) — the common event envelope
  (JSON Schema, Draft 2020-12).
- [`events/CATALOG.md`](events/CATALOG.md) — the canonical event catalog: allowed namespaces,
  the MVP event list, and the per-event documentation template (ADR-006 / ADR-0004).
- `tests/` — contract tests (schema validity and envelope conformance).

Per-service OpenAPI specs and per-event payload schemas are added as their services are
implemented (for example, `openapi/ticket-service.v1.yaml`).
