# DECISION_LOG — Decision Log

Record of the fixed architectural and process decisions for the Solva Appeals Platform.

**Document status:** approved at the planning stage (before any code is written).
**Precedence:** decisions in this log take precedence over the source set `chatgpt_docs/` in
case of conflict (see [DOCUMENT_PRECEDENCE.md](DOCUMENT_PRECEDENCE.md)).

## Record format

| Field | Meaning |
|---|---|
| ID | `ADR-NNN` |
| Decision | what was decided |
| Rationale | why |
| Consequences | what follows |
| Status | `accepted` / `proposed` / `superseded` |
| Full ADR | whether a separate ADR document is required at implementation time |

---

## ADR-001. Monorepository

- **Decision:** all code (services, frontend, orchestration, contracts, infrastructure, shared
  libraries) lives in one repository.
- **Rationale:** single developer + Claude Code; simplifies atomic contract-and-consumer changes,
  unified CI, single overview.
- **Consequences:** requires clear directory boundaries and data-ownership rules inside the
  monorepo; the ban on importing one service's code from another remains.
- **Status:** accepted. **Full ADR:** no (fixed in source requirements).

## ADR-002. Coarse-grained microservice architecture

- **Decision:** services IAM, Ticket, Process Adapter, Mailbox, Document, Notification,
  Integration, BFF; Flowable as the external process engine.
- **Rationale:** boundaries for data ownership, independent testing, and AI-agent context limits.
- **Consequences:** separate database/schema and DB user per service; cross-database joins
  forbidden; inter-service interaction only via API and events.
- **Status:** accepted. **Full ADR:** no.

## ADR-003. Technology stack

- **Decision:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, RabbitMQ,
  HTTPX, aio-pika; React + TypeScript; Flowable BPMN/DMN; Docker Compose for MVP.
- **Rationale:** fixed in source requirements; a single backend language reduces load on one
  developer.
- **Consequences:** Ruff, Pyright/mypy, pytest/pytest-asyncio mandatory; UTC in storage;
  UUIDv7/ULID for internal IDs; business registration number kept separate.
- **Status:** accepted. **Full ADR:** no.

## ADR-004. Data boundaries and cross-service access ban

- **Decision:** each service owns its database; forbidden: accessing another service's DB,
  importing another service's code, cross-database joins, and direct reads of the Flowable DB.
- **Rationale:** independence, testability, context limitation.
- **Consequences:** all inter-service data flows via REST/events; projections and read-models are
  built locally.
- **Status:** accepted. **Full ADR:** no.

## ADR-005. Task reorder: TASK_03A before TASK_02

- **Decision:** the original TASK_03 (Documents) is split into **TASK_03A (Document Foundation)**
  and **TASK_03B (Document Hardening)**. Order: `TASK_00 → TASK_01 → TASK_03A → TASK_02 →
  TASK_03B → TASK_04 → TASK_05 → TASK_06`.
- **Rationale:** the BPMN process (`chatgpt_docs/docs/04_FLOWABLE_PROCESS.md`) contains
  "completeness check" and "request documents" user tasks that need the Document Service. The
  original order placed Flowable (TASK_02) before Documents (TASK_03) — a hidden dependency.
- **Consequences:** TASK_03A provides a minimal Document Service (metadata, local storage,
  upload/download/list, link, hash, MIME/size, mock scan) before Flowable; TASK_03B (versions,
  preview, antivirus, audit, soft delete, GridFS readiness) comes after. Source
  `chatgpt_docs/tasks/TASK_*` files are not modified.
- **Status:** accepted. **Full ADR:** no (fixed here).

## ADR-006. Canonical event namespace

- **Decision:** canonical events use the `mail.*`, `ticket.*`, `response.*` namespaces, plus
  `process.*`, `document.*`, `notification.*` from
  `chatgpt_docs/docs/05_API_AND_EVENT_CONTRACTS.md`. `email.*` and the ambiguous
  `response.returned` are **forbidden**.
- **Rationale:** three documents defined different names for the same flow
  (`email.send_requested`/`mail.send_requested.v1`/`email.sent`; `deadline.*`/
  `ticket.deadline_breached.v1`). A single source of truth is required.
- **Consequences:** mail delivery — `mail.send_requested.v1`/`mail.sent.v1`/`mail.send_failed.v1`;
  response lifecycle — `response.*`; deadlines — `ticket.deadline_breached.v1` (plus a warning as
  `ticket.deadline_warning.v1`, to be confirmed in the event catalog). Notification subscribes to
  canonical events instead of `customer.reply_received`/`response.returned`.
- **Status:** accepted. **Full ADR:** yes — [`docs/adr/ADR-0004-event-catalog.md`](adr/ADR-0004-event-catalog.md) (single catalog + envelope JSON Schema).

## ADR-007. Shared-library boundaries

- **Decision:** shared packages in `libs/` are limited to **observability** (structured logging,
  correlation ID, metrics, health), **HTTP support** (client, middleware, error normalization,
  RFC 7807 Problem Details), and **testing** (fixtures, contract helpers).
- **Rationale:** reduce duplication for a single developer without breaking service isolation.
- **Consequences:** shared domain models, shared SQLAlchemy models, shared business events, and
  shared permission rules are **forbidden** — each service implements them independently. The
  event envelope as a schema (not as a shared domain class) is allowed in contracts.
- **Status:** accepted. **Full ADR:** yes — `ADR-SHARED-LIBS` at TASK_00A.

## ADR-008. ResponseDraft ownership

- **Decision:**
  - **Ticket Service** — response text, versions, approval status;
  - **Document Service** — the response PDF file;
  - **Mailbox Service** — delivery to the customer;
  - **Flowable** — the approval process and send authorization.
- **Rationale:** the BFF had `/responses`, `/approve`, `/send` endpoints, but no service owned the
  response entity.
- **Consequences:** sending is possible only after Flowable authorization; Mailbox sends by
  document ID and confirmed recipient; text/versions are not duplicated across services.
- **Status:** accepted. **Full ADR:** yes — `ADR-RESPONSE-LIFECYCLE` at TASK_02/TASK_04.

## ADR-009. SLA and business-calendar ownership

- **Decision:** **Ticket Service** computes `internal_due_at`/`legal_due_at` from a versioned SLA
  policy and business calendar (working hours, KZ holidays); **Flowable** sets timers based on the
  computed deadlines; **Notification Service** notifies about approaching/breached deadlines.
- **Rationale:** deadlines are regulatory data and part of the card (Ticket Service ownership);
  timers are part of the process (Flowable); notifications belong to Notification.
- **Consequences:** a business-calendar module and versioned SLA policy are needed in Ticket
  Service; breach is emitted as `ticket.deadline_breached.v1`.
- **Status:** accepted. **Full ADR:** yes — [`docs/adr/ADR-0005-sla-and-business-calendar.md`](adr/ADR-0005-sla-and-business-calendar.md) (SLA policy + business calendar + platform timezone).

## ADR-010. Completeness check is a human task in MVP

- **Decision:** in MVP the completeness check is a human task. **DMN** defines the required
  document codes; **Document Service** stores the actual documents; the **employee** confirms the
  result.
- **Rationale:** automatic document classification is a future AI capability, out of MVP scope.
- **Consequences:** the `required − verified detected = missing` calculation is performed by the
  employee; AI hooks stay disabled.
- **Status:** accepted. **Full ADR:** no.

## ADR-011. Reporting via a read-model inside Ticket Service

- **Decision:** MVP reporting is implemented as a reporting/read-model module **inside Ticket
  Service**, updated by events.
- **Rationale:** a separate reporting service is excessive for one developer; Ticket Service
  already owns analytics, satisfaction, and systemic issues.
- **Consequences:** cross-service SQL and direct reads of the Flowable DB are **forbidden**;
  process data arrives via projection events; a separate reporting service is deferred.
- **Status:** accepted. **Full ADR:** yes — `ADR-REPORTING-READ-MODEL` at TASK_05.

## ADR-012. Mocks for undefined external integrations

- **Decision:** for Exchange, corporate SSO/OIDC, and the core accounting system, create an
  interface + fake/mock; real adapters come after access is granted.
- **Rationale:** development must not be blocked on corporate access; the source requirements
  mandate this.
- **Consequences:** `FakeMailboxProvider` + EML fixtures, dev-auth (non-production only),
  `FakeCoreSystemAdapter`; assumptions documented in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
- **Status:** accepted. **Full ADR:** no.

## ADR-013. Bootstrap without scaffolding all services

- **Decision:** TASK_00A creates the monorepo skeleton, the shared library, and **one
  demonstration service + template**; remaining services are created as their tasks are
  implemented.
- **Rationale:** avoid premature code and dead scaffolds; focus the session context.
- **Consequences:** the directory structure and template are fixed early but filled incrementally.
- **Status:** accepted. **Full ADR:** no.

## ADR-014. File storage: local in MVP, GridFS/Document API later

- **Decision:** MVP — `LocalFileStorage`/`NetworkFileStorage` + metadata in PostgreSQL,
  `storage_backend=local`; later — `GridFSStorage`/corporate Document API with dual-read and
  background migration keeping `document_id` unchanged.
- **Rationale:** fixed in source requirements; MongoDB is out of MVP.
- **Consequences:** a `FileStorage` protocol from the start; the API does not change when GridFS
  is added.
- **Status:** accepted. **Full ADR:** yes — `ADR-STORAGE-MIGRATION` at TASK_03B.

## ADR-015. English-only technical code and documentation

- **Decision:** all technical artifacts (source code, identifiers, docstrings, code comments,
  technical logs, tests, OpenAPI descriptions, JSON Schema descriptions, ADRs, architecture
  documents, service and root README files, SERVICE_MAP files, technical planning documents in
  root `docs/` and `tasks/`, CI/CD documentation, runbooks, deployment documentation) are written
  in **English**. **Conversation with the user stays in Russian.** Business/regulatory content
  (UI text, customer-facing messages, response templates, classifier display names, regulatory
  quotations, business requirements, and Russian/Kazakh test fixtures) may remain in Russian or
  Kazakh. Source documents under `chatgpt_docs/` remain unchanged and may remain in Russian.
- **Rationale:** consistency, maintainability, compatibility with tooling and international
  engineering standards, and improved AI-agent context.
- **Consequences:** business and regulatory source content may remain in Russian while all
  implementation-facing materials are in English; the nine planning documents were translated to
  English; a root `CLAUDE.md` carries the mandatory rules; documentation coverage and English
  Markdown checks are added to CI quality gates; the Definition of Done is extended (see
  [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and root `CLAUDE.md`).
- **Status:** accepted. **Full ADR:** yes — [`docs/adr/ADR-0002-language-and-code-documentation-policy.md`](adr/ADR-0002-language-and-code-documentation-policy.md).

## ADR-016. Vendor-neutral code naming

- **Decision:** code identifiers, package names, module names, and distribution names must not
  contain the vendor name "solva"; use the neutral prefix `mfo` (for example, `mfo-observability`,
  `mfo_http`). The product/organization name ("Solva Appeals Platform") may still appear in
  documentation prose and user-facing/business content where accurate.
- **Rationale:** avoid brand coupling in code, improve portability and reusability, and keep the
  codebase vendor-neutral while preserving the meaningful product name in documentation.
- **Consequences:** the bootstrap shared libraries were named `mfo-*` (renamed from initial
  `solva-*`); imports use `mfo_*`; a naming check may be added to CI later. Business/user-facing
  text is unaffected.
- **Status:** accepted. **Full ADR:** yes — [`docs/adr/ADR-0003-vendor-neutral-code-naming.md`](adr/ADR-0003-vendor-neutral-code-naming.md).

---

## ADRs to prepare at implementation time

| Code | Topic | Prepare at phase | Status |
|---|---|---|---|
| ADR-0001 (shared-libraries) | `libs/` boundaries (observability/http/testing) | TASK_00A | Written |
| ADR-0002 (language-policy) | English-only code/docs, Google docstrings, doc coverage | TASK_00A | Written |
| ADR-0003 (vendor-neutral-naming) | No `solva` in code identifiers; `mfo` prefix | TASK_00A | Written |
| ADR-0004 (event-catalog) | Single event catalog + envelope JSON Schema, versioning | TASK_00C | Written |
| ADR-0005 (sla-calendar) | SLA policy + business calendar + platform timezone, due_at computation | TASK_01C | Written |
| ADR-0006 (dev-auth-authorization) | Dev/local JWT auth, bcrypt hashing, and the role→permission matrix (per-service enforcement) | TASK_01D | Written |
| ADR-0007 (bff-gateway) | BFF auth context via IAM `/auth/me`, gateway permission enforcement, workspace aggregation with flagged partial failures, stateless empty schema | TASK_01E-1 | Written |
| ADR-0008 (ticket-authorization) | Ticket-service independent JWT verification, permission + fail-closed data-scope/confidentiality policy, and server-derived trusted actor | TASK_01E-1 (remediation) | Written |
| ADR-RESPONSE-LIFECYCLE | Response lifecycle draft→approve→send | TASK_02 / TASK_04 |
| ADR-REPORTING-READ-MODEL | Reporting read-model in Ticket Service | TASK_05 |
| ADR-STORAGE-MIGRATION | Dual-read and file migration to GridFS | TASK_03B | Pending |
| ADR-AUTH-OIDC | Transition dev-auth → corporate OIDC | TASK_06 | Pending |
