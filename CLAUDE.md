# CLAUDE.md — Mandatory Project Rules (Root)

Root engineering rules for the Solva Appeals Platform. These rules take precedence over
`chatgpt_docs/CLAUDE.md`, which is a **read-only source** document and must not be modified
(see [docs/DOCUMENT_PRECEDENCE.md](docs/DOCUMENT_PRECEDENCE.md)). The original architectural
constraints and data-ownership rules from `chatgpt_docs/CLAUDE.md` remain in force; this file
adds the approved language and documentation policy on top of them.

## Before starting a task

1. Read `chatgpt_docs/docs/00_MASTER_SPEC.md`.
2. Read the current subtask entry in `tasks/DETAILED_TASK_INDEX.md`.
3. Read the specs of the affected services only.
4. Read `docs/DECISION_LOG.md` and `docs/CONTEXT_LOADING_GUIDE.md` for the phase.
5. State a short plan and list the files you expect to change.

## Architectural prohibitions (from source requirements)

- Do not access another service's database.
- Do not import one service's code from another service.
- Do not store binary files in RabbitMQ.
- Do not store PDFs, images, or full emails in Flowable variables.
- Do not give the frontend direct access to Flowable or the filesystem.
- Do not add infrastructure without an ADR.
- Do not put business logic in FastAPI route handlers.
- Do not perform irreversible migrations without a plan.
- Do not delete regulatory data through an ordinary user action.
- Do not give AI services direct access to Exchange or application databases.

## Data ownership

Ticket Service (card, classification, decision, analytics, reporting read-model),
Flowable (process, tasks, assignments, timers, approvals), Mailbox Service (inbound/outbound
mail), Document Service (files, versions, hashes, downloads), IAM Service (users, roles, teams),
Notification Service (notifications), Integration Service (internal-system adapters).
See `docs/DECISION_LOG.md` (ADR-008/009/010/011) for ResponseDraft, SLA, completeness, and
reporting ownership.

## Contracts

Change OpenAPI/JSON Schema and contract tests first, then the implementation. Events carry
`eventId`, `eventType`, `eventVersion`, `occurredAt`, `producer`, `correlationId`,
`causationId`, `payload`. Consumers are idempotent. Publishing uses the Transactional Outbox.
Canonical event namespaces are `mail.*`, `ticket.*`, `response.*`, `process.*`, `document.*`,
`notification.*` (ADR-006). `email.*` and `response.returned` are forbidden.

## Code standards

Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, HTTPX, aio-pika; Ruff, Pyright/mypy;
pytest, pytest-asyncio; UTC in storage; UUIDv7/ULID for internal IDs; separate business
registration number; strict typing.

---

## Language policy (ADR-015)

**Conversation with the user stays in Russian.** All chat communication — questions,
explanations, plans shown in chat, progress reports, summaries, error/blocker descriptions,
decision requests, final reports, recommendations, and warnings — is written in Russian, unless
the user explicitly requests otherwise. When presenting changes made to an English technical
artifact, explain them to the user in Russian. When offering architectural/technical options,
ask and describe options and recommendation in Russian, using English technical terms only where
they improve precision.

**English is mandatory for all technical artifacts**, including: source-code identifiers; module,
package, class, function, method, variable, and constant names; docstrings; inline comments;
TODO/FIXME comments; developer-facing exception messages; structured log messages; test names and
descriptions; commit-message recommendations; service and root README files; architecture
documentation; ADRs; API documentation; OpenAPI summaries/descriptions; JSON Schema
titles/descriptions; event-catalog descriptions; database-migration descriptions; SERVICE_MAP
files; deployment docs; runbooks; troubleshooting guides; implementation-status documents;
monitoring/alert descriptions; technical diagrams and labels; CI/CD documentation; technical
acceptance reports; and all technical planning documents in root `docs/` and `tasks/`.

**Russian and Kazakh are allowed only for business content:** UI labels and user-facing messages;
regulated document names; classifier display values; customer response templates; exact
regulatory quotations; approved business terminology; and test fixtures that specifically
validate Russian or Kazakh content.

**Source requirements under `chatgpt_docs/` remain in Russian and are read-only.**

**Vendor-neutral code naming (ADR-016):** code identifiers, package names, module names, and
distribution names must not contain the vendor name "solva". Use the neutral prefix `mfo` (for
example, `mfo-observability`, `mfo_http`). The product name ("Solva Appeals Platform") may still
appear in documentation prose and user-facing/business content where accurate.

## Code documentation requirements

- Every module has a module-level docstring.
- Every class has a class docstring (entities, value objects, application services, repositories,
  adapters, HTTP clients, event consumers, workers, configuration classes, exception classes,
  test helper classes).
- Every function and method has a docstring (public and private helpers, async functions,
  FastAPI route handlers, dependency providers, event handlers, message consumers, repository
  methods, migration functions, background jobs, test functions, fixtures).
- Do not leave functions undocumented because the implementation looks simple.
- Docstrings must be useful — describe purpose, responsibility, args, returns, raised exceptions,
  side effects, external calls, transaction boundaries, idempotency, security implications, and
  important invariants where applicable. Do not merely repeat names or type annotations.

**Convention: Google-style docstrings** across the whole project.

## Comments policy

Comments explain **why**, not **what**. Add comments for non-obvious business rules, regulatory
constraints, concurrency, idempotency, retries, transaction boundaries, security decisions,
temporary compatibility code, workarounds, complex SQL, Flowable integration behavior, and
unusual library limitations. Do not add obvious, redundant, decorative, or outdated comments.

Every TODO contains a short reason, the target task/issue identifier, and the removal condition,
e.g. `# TODO(TASK_04C): Replace polling with Exchange change notifications after the corporate
application registration is approved.`

## Documentation quality gates (CI)

- Ruff docstring rules (`D`) enabled with the Google convention.
- Docstring-coverage check targeting 100% for maintained project code (e.g. `interrogate` or an
  AST-based script) covering modules, classes, functions, methods, private helpers, tests,
  fixtures, and migration functions.
- Validation that technical Markdown files are written in English.
- Review of outdated comments during code changes.
- Excluded only (each exclusion explicit and documented): generated code, empty `__init__.py`
  where the convention allows, third-party vendored code, and generated migration internals that
  cannot reasonably be modified.

## Per-service documentation (when behavior changes)

Each service maintains: `README.md`, `SERVICE_MAP.md`, local config reference, local dev
instructions, API overview, owned data, emitted events, consumed events, external dependencies,
failure behavior, migration instructions, testing instructions, and known limitations.

## Definition of Done (applies to every implementation task)

1. Acceptance criteria met.
2. Tests added and passing.
3. Migrations verified (migration/backfill/rollback/validation for data changes).
4. OpenAPI and event schemas current and passing contract tests.
5. No cross-service DB dependencies; security check performed.
6. Docker build works; health endpoints; compose smoke test passes.
7. Every new/modified module, class, function, and method has an **English** docstring.
8. Non-obvious behavior has appropriate **English** comments; no redundant comments.
9. OpenAPI and event-schema descriptions updated.
10. Service `README.md` and `SERVICE_MAP.md` updated where behavior changed; architecture docs
    updated where boundaries changed.
11. Documentation checks pass in CI.
12. No Russian-language technical comments or docstrings introduced; user-facing Russian/Kazakh
    text is separated into the localization/business-content layer.

## Undefined external integrations

Create an interface, a fake/mock, and document the assumption. Do not invent real credentials or
endpoints. See ADR-012 and [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md).

## AI

AI output is stored separately from confirmed data. AI may recognize, classify, extract, and draft.
AI may not decide restructuring, change a contract, close a ticket, choose an arbitrary recipient,
or send a legally significant refusal. AI never receives Exchange/DB credentials; documents are
untrusted; sending is authorized only by Flowable.
