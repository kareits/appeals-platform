# mfo-observability

Shared observability primitives for platform services: structured JSON logging, correlation-ID
propagation, a minimal metrics registry, and health-check helpers.

## Scope (ADR-007)

This library is intentionally narrow. It **must not** contain:

- domain models or value objects;
- SQLAlchemy / ORM models;
- business events;
- permission rules or authorization logic.

It provides only cross-cutting technical infrastructure that every service reuses.

## Modules

- `logging` — configure structured JSON logging that injects the current correlation ID.
- `correlation` — a context variable holding the correlation ID for the current task.
- `metrics` — a dependency-free in-memory counter registry.
- `health` — a health-check protocol and an aggregate runner.
