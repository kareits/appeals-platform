# ADR-0003: Vendor-neutral code naming

- **Status:** Accepted
- **Related:** DECISION_LOG ADR-016

## Context

The platform is built for the "Solva" organization, but tying code identifiers to the vendor name
reduces portability and reusability, and couples the codebase to a specific brand. The product name
remains meaningful in documentation and user-facing content.

## Decision

Code identifiers, package names, module names, and distribution names **must not** contain the
vendor name "solva". Use the neutral prefix `mfo` (micro-finance organization) instead — for
example, `mfo-observability`, `mfo_http`.

The product/organization name ("Solva Appeals Platform") may still appear in documentation prose,
UI text, and other business/user-facing content where it is accurate.

## Alternatives considered

- **Use `solva` as the code prefix:** rejected — brand coupling, reduced reusability.
- **Use a generic prefix such as `platform` or `app`:** rejected — less descriptive than `mfo`,
  which conveys the domain (micro-finance organization) without vendor lock-in.

## Consequences

- Shared libraries and packages are named `mfo-*`; imports use `mfo_*`.
- Documentation may reference the real product name for clarity.
- A lightweight naming check can be added to CI later to guard against reintroducing `solva` in
  code identifiers.

## Migration impact

The initial bootstrap libraries were renamed from `solva-*` to `mfo-*` before any release.

## Rollback considerations

Naming is mechanical; a superseding ADR plus a rename would reverse it.
