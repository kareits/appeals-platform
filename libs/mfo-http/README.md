# mfo-http

Shared HTTP support for platform services: correlation-ID middleware, an HTTP client wrapper that
propagates the correlation ID, and RFC 7807 Problem Details error handling.

## Scope (ADR-007)

Technical HTTP concerns only. This library **must not** contain domain models, ORM models,
business events, or permission rules.

## Modules

- `errors` — RFC 7807 Problem Details model, a raising exception, and Starlette exception handlers.
- `middleware` — ASGI middleware that reads or generates the correlation ID and binds it to the
  request context and response headers.
- `client` — an `httpx.AsyncClient` wrapper that injects the correlation header and a default
  timeout.

Depends on `mfo-observability` for correlation-ID propagation.
