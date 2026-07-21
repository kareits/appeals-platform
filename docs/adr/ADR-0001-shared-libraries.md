# ADR-0001: Shared library boundaries

- **Status:** Accepted
- **Related:** DECISION_LOG ADR-007

## Context

A single developer maintains a coarse-grained microservice monorepo. Cross-cutting technical
concerns (structured logging, correlation IDs, metrics, health checks, HTTP client behavior, error
normalization, test helpers) recur in every service. Duplicating them is wasteful, but sharing
domain code would couple services and violate their data-ownership boundaries (ADR-002, ADR-004).

## Decision

Provide shared libraries under `libs/`, limited to three distributions:

- `mfo-observability` — structured logging, correlation-ID propagation, a minimal metrics
  registry, and health-check primitives;
- `mfo-http` — an HTTP client wrapper, correlation-ID middleware, and RFC 7807 Problem Details;
- `mfo-testing` — pytest/ASGI test helpers and contract-test utilities.

The libraries **must not** contain domain models, ORM models, business events, or permission
rules. Those are implemented independently in each service.

## Alternatives considered

- **No shared libraries (copy per service):** rejected — high duplication and drift for one
  developer.
- **A single "common" package including domain helpers:** rejected — would become a coupling point
  and erode service boundaries.
- **A shared events/permissions library:** rejected — business semantics belong to owning services.

## Consequences

- Reduced duplication for technical concerns with stable, well-tested primitives.
- A clear, enforceable boundary: reviewers reject domain/business content in `libs/`.
- `mfo-http` depends on `mfo-observability` for correlation; library-to-library dependencies among
  platform libs are acceptable.

## Migration impact

None (greenfield). New services depend on the libraries from creation.

## Rollback considerations

If a library proves too broad, split or remove it; because services depend only on narrow
technical APIs, replacement is localized.
