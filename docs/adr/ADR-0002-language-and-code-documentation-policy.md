# ADR-0002: Language and code-documentation policy

- **Status:** Accepted
- **Related:** DECISION_LOG ADR-015

## Context

The project has Russian-language business and regulatory source requirements (`chatgpt_docs/`) but
must produce maintainable, tool-compatible code. Mixing languages in code and technical docs hurts
consistency, tooling, and AI-agent context. The developer and stakeholders communicate in Russian.

## Decision

- **Technical artifacts are English:** source code, identifiers, docstrings, comments, technical
  logs, tests, OpenAPI/JSON Schema descriptions, ADRs, architecture docs, service and root READMEs,
  SERVICE_MAP files, technical planning documents in `docs/` and `tasks/`, CI/CD docs, runbooks.
- **User conversation is Russian:** questions, explanations, plans in chat, reports, and
  recommendations are in Russian; changes to English artifacts are explained in Russian.
- **Business content may be Russian/Kazakh:** UI text, customer messages, response templates,
  classifier display names, regulatory quotations, business requirements, and localized test
  fixtures.
- **Source `chatgpt_docs/` stays Russian and read-only.**
- **Docstrings:** Google convention on every module, class, function, and method (including tests,
  fixtures, and migration functions).
- **Enforcement in CI:** Ruff `D` rules; a docstring-coverage gate targeting 100% for maintained
  code (documented exclusions only); an English-Markdown check for technical docs.

## Alternatives considered

- **Russian technical artifacts:** rejected — poor tooling/ecosystem fit and AI-context quality.
- **English everywhere including conversation:** rejected — the team works in Russian.
- **Docstrings only on public APIs:** rejected — private helpers, tests, and migrations also need
  documentation for maintainability.

## Consequences

- Consistent, tool-friendly, internationally readable code and docs.
- Extra authoring discipline; mitigated by automated gates and templates.
- The nine planning documents were translated to English; a root `CLAUDE.md` carries the rules.

## Migration impact

Existing English planning documents remain; future technical artifacts must comply. CI gates block
non-compliant changes.

## Rollback considerations

Policy is documentation/process; it can be relaxed via a superseding ADR without code changes.
