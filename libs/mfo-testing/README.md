# mfo-testing

Shared testing helpers for platform services: reusable pytest fixtures and small contract-test
utilities.

## Scope (ADR-007)

Technical test support only. This library **must not** contain domain models, ORM models, business
events, or permission rules.

## Modules

- `asgi` — build an `httpx.AsyncClient` bound to an ASGI application for in-process API tests.
- `contracts` — assertion helpers for validating payloads against a JSON Schema.
