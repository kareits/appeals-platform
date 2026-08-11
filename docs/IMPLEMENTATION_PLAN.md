# IMPLEMENTATION_PLAN — Engineering Plan by Phase

Detailed implementation plan. Phase order follows [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md) and
ADR-005. Each phase is described using the template below; session-sized subtasks are in
[tasks/DETAILED_TASK_INDEX.md](../tasks/DETAILED_TASK_INDEX.md).
API/event conventions — `chatgpt_docs/docs/05_API_AND_EVENT_CONTRACTS.md`; canonicalization —
ADR-006. Language and documentation rules — ADR-015 and root `CLAUDE.md`.

**Field legend:** Goal · Inputs · Services · Components · API · Events · Data
(migration/backfill/rollback/validation) · Tests · Acceptance · Result · Dependencies · Out of scope.

---

## Documentation quality gates (apply to every EP that produces code)

Per ADR-015 and root `CLAUDE.md`:

- Ruff docstring rules (`D`) enabled with the Google docstring convention.
- Docstring-coverage check targeting 100% for maintained project code (e.g. `interrogate` or an
  AST-based script) covering modules, classes, functions, methods, private helpers, tests,
  fixtures, and migration functions. Documented exclusions only.
- CI validation that technical Markdown files are in English.
- Outdated-comment review during code changes.
- OpenAPI summaries/descriptions and JSON Schema titles/descriptions written in English; each
  endpoint documents summary, description, authorization, request/response semantics, error
  responses, and idempotency; each event schema documents producer, consumers, trigger, payload
  semantics, delivery guarantees, idempotency, versioning, and personal-data classification.

These gates are established in EP-0 (TASK_00A/00C) and enforced from then on.

---

## EP-0 · TASK_00 (A–C) — Repository Bootstrap

- **Goal:** monorepo and infrastructure foundation without business features.
- **Inputs:** `chatgpt_docs/tasks/TASK_00`, `docs/00`, `docs/03`, `docs/05`; ADR-007, ADR-013,
  ADR-015.
- **Services:** monorepo skeleton; **one demo service** + template (ADR-013). Other services are
  not created.
- **Components:** directories `apps/ services/ orchestration/ contracts/ infrastructure/ libs/`;
  Python workspace; `libs/` (observability: logging/correlation/metrics/health; http:
  client/middleware/RFC7807; testing: fixtures/contract helpers); Dockerfile template;
  docker-compose (PostgreSQL, RabbitMQ, Flowable, reverse proxy); `.env.example`; Makefile/task
  runner (up/down/test/lint/migrate); Ruff (incl. `D` rules)/type checker/pytest; docstring
  coverage tool; English-Markdown check; CI.
- **API:** `/health/live`, `/health/ready` on the demo service.
- **Events:** `event-envelope.v1.json` (schema with
  `eventId/eventType/eventVersion/occurredAt/producer/correlationId/causationId/payload`).
- **Data:** sample migration for the demo service. Rollback: `alembic downgrade`. Validation: the
  migration applies and rolls back in CI. (No backfill.)
- **Tests:** lint/type/test in CI; compose smoke (health available); sample migration passes;
  docstring-coverage and English-Markdown checks pass.
- **Acceptance:** `docker compose up --build` starts; health available; Flowable only on
  dev/private network; no secrets; CI green (including documentation gates).
- **Result:** a reproducible skeleton on which services are built.
- **Dependencies:** none.
- **Out of scope:** scaffolding all services, business logic, domain models.

## EP-0F · TASK_00D — Flowable Spike (technical)

- **Goal:** validate the Process Adapter ↔ Flowable loop before the business process; de-risk
  Flowable.
- **Inputs:** `docs/04`, `services/PROCESS_ADAPTER.md`; EP-0 result.
- **Services:** Process Adapter (minimal, technical).
- **Components:** Flowable REST client (HTTPX); a test BPMN (one user task + one timer + one
  message event, no domain); operations: start process, list user tasks, claim, complete, timer
  fire (accelerated), message correlation, read history.
- **API:** internal adapter methods (not a public contract).
- **Events:** none (spike).
- **Data:** separate Flowable DB (from EP-0); the adapter has no own domain schema at this step.
- **Tests:** integration against a running Flowable in compose; accelerated timer; idempotent
  start by business key.
- **Acceptance:** the start→task→claim→complete→timer→message→history loop is reproducible from
  FastAPI; behavior documented.
- **Result:** a validated integration pattern + notes for EP-3.
- **Dependencies:** EP-0.
- **Out of scope:** business-process BPMN, DMN, projection events, UI.

## EP-1 · TASK_01 — Ticket and Manual Workflow

- **Goal:** manual registration and the regulatory register before Flowable; a vertical slice.
- **Inputs:** `docs/01`, `docs/02`, `services/TICKET_SERVICE.md`, `services/IAM_SERVICE.md`,
  `services/BFF_SERVICE.md`; ADR-009 (due_at).
- **Services:** Ticket Service, IAM Service, BFF, web-frontend.
- **Components:** Ticket model + applicant/representative + classifications + dictionaries +
  decision + related tickets + comments; registration-number generator (business number separate
  from UUID); close validation; retention (`retention_until`, `legal_hold`); audit; SLA policy +
  business calendar (computing `internal_due_at`/`legal_due_at`); IAM dev-users/roles +
  authorization matrix; BFF (auth context, workspace aggregation, error normalization); frontend
  (login, list/search, manual-registration form, card, comments, decision/close) followed by a
  design/UI-polish pass (01E-5) that applies a consistent visual design and accessibility over those
  screens (presentation only; supersedes ADR-0009's minimal-styling scope via a new ADR). User-facing
  Russian/Kazakh text stays in the localization layer (ADR-015).
- **API:** `GET/POST /tickets`, `GET /tickets/{id}/workspace`, `PATCH /tickets/{id}`,
  `POST /tickets/{id}/comments`; `/api/v1`, camelCase, RFC7807, `X-Correlation-ID`,
  `Idempotency-Key` for commands, optimistic locking.
- **Events:** `ticket.created.v1`, `ticket.classified.v1`, `ticket.updated.v1`,
  `ticket.decision_recorded.v1`, `ticket.closed.v1` (via Transactional Outbox).
- **Data:** Ticket and IAM migrations. Backfill: seed dictionaries/classifiers/roles (fixtures).
  Rollback: downgrade + plan for irreversibility (regulatory data is not deleted). Validation:
  invariants (unique registration number, required fields, nullable conditionals) covered by tests.
- **Tests:** unit (invariants, close validation, SLA computation), integration
  (registration/search), regulatory tests (nullable conditionals, close blocked without decision,
  first-line read-only, audit).
- **Acceptance:** any written appeal can be registered; conditional fields nullable; required
  fields validated; unique number; search/filter; first-line read-only; close blocked without
  decision; audit; regulatory tests green.
- **Result:** a working end-to-end registration→decision→close flow with a placeholder status.
- **Dependencies:** EP-0.
- **Out of scope:** Flowable (placeholder status), documents, mail, reporting.
- **Note:** status changes only through the projection mechanism (in EP-1 a placeholder; the API
  is ready for Flowable).

## EP-2 · TASK_03A — Document Foundation

- **Goal:** a minimal Document Service for real BPMN operation (ADR-005).
- **Inputs:** `docs/02` (Document metadata), `services/DOCUMENT_SERVICE.md`, `docs/06`
  (attachments); ADR-014.
- **Services:** Document Service.
- **Components:** document metadata; `FileStorage` protocol; `LocalFileStorage`;
  upload/download(stream)/list; `document_id ↔ ticket_id` link; SHA-256; random storage key; MIME
  validation; size limits; mock scan status; persistent volume; `storage_backend=local`.
- **API:** `contracts/openapi/document-service.v1.yaml`; upload/stream/list/link.
- **Events:** `document.uploaded.v1`, `document.available.v1` (mock scan → CLEAN/AVAILABLE).
- **Data:** document-metadata migration. Backfill: none. Rollback: downgrade; volume files are not
  deleted by migration. Validation: hash stored and verified; no binary in RabbitMQ.
- **Tests:** unit (hash, MIME, size, key), integration (upload→list→download), contract tests.
- **Acceptance:** restart does not lose files; other services use document ID only; no path
  traversal; pending/infected inaccessible; hash verified; no binary events; GridFS can be added
  without API change.
- **Result:** a file boundary usable for BPMN completeness and mail attachments.
- **Dependencies:** EP-0; ticket linkage — EP-1 (ticket_id).
- **Out of scope:** versions, preview, real antivirus, download audit, soft delete, cleanup,
  GridFS (→ EP-4).

## EP-3 · TASK_02 — Flowable Integration

- **Goal:** replace the placeholder workflow with BPMN/DMN; a full process.
- **Inputs:** `docs/04`, `services/PROCESS_ADAPTER.md`, `orchestration/README.md`; EP-0F result;
  ADR-008, ADR-009, ADR-010.
- **Services:** Process Adapter, Flowable (orchestration), Ticket Service (projection consumer),
  BFF/frontend (tasks).
- **Components:** BPMN `appeal_restructuring_v1`; DMN `appeal_routing_v1` (inputs
  `product_code/classifier_code/category/source_channel/complaint_flag/ombudsman_flag/...`;
  outputs `team_code/priority_code/internal_sla_policy/approval_policy/required_document_ruleset`);
  Process Adapter (start/list/claim/complete/reassign/hold/resume/correlate reply/handle email
  sent); WAITING(5d)/HOLD(15d) timers; approval branch; projection events; process audit;
  versioned deployment; UI (task list/queues, claim/complete/reassign, SLA/deadlines,
  hold/resume). Completeness is a human task (ADR-010). SLA: Ticket computes due_at, Flowable sets
  the timer (ADR-009).
- **API:** `contracts/openapi/process-adapter.v1.yaml`; BFF
  `POST /tickets/{id}/tasks/{taskId}/complete`, `POST /tickets/{id}/reassign`.
- **Events:** `process.started.v1`, `process.task_created.v1`, `process.assignment_changed.v1`,
  `process.status_changed.v1`, `process.completed.v1`; `ticket.deadline_breached.v1`. Ticket
  Service updates the projection from these events (idempotently).
- **Data:** Process Adapter migrations (ticket/process/task mapping, idempotency, projection
  outbox). Backfill: none. Rollback: downgrade; active Flowable processes are not migrated
  automatically (versioned deployment). Validation: one ticket → one process (business key).
- **Tests:** integration (DMN assignment, authorized completion), accelerated timer tests
  (WAITING/HOLD), projection eventual consistency, duplicate events safe, no direct status edit,
  email response does not close.
- **Acceptance:** one ticket→one process; DMN assignment; authorized completion; timers
  (accelerated) fire; no direct status editing; email response does not close; projection
  converges; duplicate events safe.
- **Result:** a real, managed appeal process.
- **Dependencies:** EP-1 (card/projection), EP-2 (documents for completeness), EP-0F (Flowable
  loop).
- **Out of scope:** real mail (EP-5), document hardening (EP-4), reporting (EP-6).

## EP-4 · TASK_03B — Document Hardening

- **Goal:** bring the Document Service to production-grade security without MongoDB.
- **Inputs:** `services/DOCUMENT_SERVICE.md`, `docs/06`, `docs/07` (hashes/versions); ADR-014.
- **Services:** Document Service.
- **Components:** document versions + AddVersion; safe preview; scanner interface + full antivirus
  integration (states UPLOADING…INFECTED/DELETED); download audit; soft delete (not purge);
  cleanup jobs; GridFS readiness (dual-read, unchanged document_id).
- **API:** extend `document-service.v1.yaml` (versions, preview, audit) without breaking changes.
- **Events:** `document.scan_failed.v1`, `document.deleted.v1`.
- **Data:** migrations (versions, statuses, deleted_at, migrated_at). Backfill: set `version=1`
  for existing documents. Rollback: downgrade; soft delete does not delete files. Validation:
  pending/infected inaccessible; versions preserved; download audit written.
- **Tests:** integration (versions, preview, scan states, download audit, soft delete), security
  (traversal, MIME, size).
- **Acceptance:** versions preserved; INFECTED/PENDING inaccessible; downloads audited; soft
  delete ≠ purge; GridFS can be added without API change.
- **Result:** secure storage, ready for mail and production.
- **Dependencies:** EP-2, EP-3.
- **Out of scope:** the real GridFS data migration (post-MVP), corporate Document API.

## EP-5 · TASK_04 — Exchange Email

- **Goal:** mail integration via a provider abstraction (Fake until corporate access).
- **Inputs:** `services/MAILBOX_SERVICE.md`, `docs/02` (mail message), `docs/06` (email);
  ADR-006, ADR-008, ADR-012.
- **Services:** Mailbox Service, Document Service (attachments), Ticket Service (ticket creation
  from mail), Process Adapter (reply correlation, handle email sent).
- **Components:** provider interface; `FakeMailboxProvider` + EML fixtures + outbound capture;
  poll/checkpoint; dedup (external/internet message IDs); body html/text; attachments via Document
  Service; ticket creation from mail; reply linking (conversation/in-reply-to/references);
  reconciliation; outbound send (approved only, verified recipient, fixed sender, documents by ID,
  idempotency, delivery attempts); ticket number in subject.
- **API:** `contracts/openapi/mailbox-service.v1.yaml`.
- **Events:** `mail.received.v1`, `mail.linked.v1`, `mail.send_requested.v1`, `mail.sent.v1`,
  `mail.send_failed.v1`; response lifecycle — `response.*` (ADR-006/008). `email.*` and
  `response.returned` are **forbidden**.
- **Data:** Mailbox migrations (messages, checkpoints, delivery attempts, dedup keys). Backfill:
  none. Rollback: downgrade. Validation: a duplicate external ID does not create a second ticket;
  header-injection protection.
- **Tests:** integration (fixture → one ticket; attachments linked; duplicate ignored; reply
  linked; approved response sent once; failure retries and is visible); full timeline.
- **Acceptance:** matches TASK_04 acceptance; sending only on Flowable authorization (ADR-008).
- **Result:** mail receiving and sending via the Fake provider with a real timeline.
- **Dependencies:** EP-2 (attachments), EP-3 (process/reply/response sending).
- **Out of scope:** the real Exchange adapter (after corporate access), WhatsApp/Telegram.

## EP-6 · TASK_05 — Reporting and Audit

- **Goal:** mandatory management reporting and analytics.
- **Inputs:** `docs/01` (reporting), `docs/02` (analytics), `services/TICKET_SERVICE.md`; ADR-011.
- **Services:** Ticket Service (reporting/read-model module), BFF/frontend (reports).
- **Components:** a read-model updated by events (`ticket.*`, `process.*`, `mail.*`, `response.*`);
  reports (counts/classification by product, deadlines/compliance, satisfaction, systemic
  issues/actions, backlog aging, workload); XLSX/CSV export; root cause;
  SystemicIssue/CorrectiveAction/Satisfaction; full audit.
- **API:** `GET /reports/...` via BFF; export endpoints (audited).
- **Events:** subscribe to existing events; `notification.*` for actions if needed.
- **Data:** read-model and analytics-table migrations (SystemicIssue, CorrectiveAction,
  Satisfaction). Backfill: build the read-model from event history (replay). Rollback: downgrade
  the read-model (source events preserved). Validation: overdue computation reproducible;
  classifier history preserved.
- **Tests:** integration (filters apply to reports and exports; exports audited; classifier
  history retained; overdue reproducible; physical deletion unavailable).
- **Acceptance:** matches TASK_05; **no cross-service SQL and no direct reads of the Flowable DB**
  (ADR-011).
- **Result:** mandatory reporting and audit.
- **Dependencies:** EP-1..EP-5.
- **Out of scope:** a separate reporting service (post-MVP), BI dashboards.

## EP-7 · TASK_06 — Production Readiness

- **Goal:** pilot preparation.
- **Inputs:** `docs/06`, `tasks/TASK_06`; ADR-012 (OIDC), ADR-014.
- **Services:** all (production config), IAM (OIDC), infrastructure.
- **Components:** OIDC adapter (replacing dev-auth); production config; secrets integration; TLS;
  backup/restore (PG + file volume + Flowable DB, consistently); logs/metrics/alerts; DLQ;
  reconciliation dashboard; indexes; load/security tests; retention dry run; runbooks; user docs.
- **API:** no breaking changes; dev-auth disabled.
- **Events:** DLQ handling for all flows.
- **Data:** performance indexes and migrations. Backfill: none. Rollback: downgrade indexes.
  Validation: retention dry-run without real deletion; restore demonstrated.
- **Tests:** load, security, restore drill, retention dry-run, least-privilege check.
- **Acceptance:** no dev-auth in production; restore demonstrated; RPO/RTO recorded; dependencies
  monitored; Exchange reconciliation prevents loss; outbox prevents event loss; least privilege
  verified.
- **Result:** a platform ready for the pilot.
- **Dependencies:** EP-0..EP-6.
- **Out of scope:** Kubernetes, autonomous AI, the GridFS data migration.

---

## Definition of Done (all implementation tasks)

Base DoD plus the ADR-015 documentation requirements (full list in root `CLAUDE.md`):

1. Acceptance criteria met.
2. Tests added and passing.
3. Migrations verified (migration/backfill/rollback/validation for data changes).
4. OpenAPI/event schemas current and passing contract tests.
5. No cross-service DB dependencies; security check performed.
6. Docker build works; health endpoints; compose smoke test passes.
7. Every new/modified module, class, function, and method has an English docstring.
8. Non-obvious behavior has appropriate English comments; no redundant comments.
9. OpenAPI and event-schema descriptions updated (English).
10. Service `README.md`/`SERVICE_MAP.md` updated where behavior changed; architecture docs updated
    where boundaries changed.
11. Documentation checks pass in CI (docstring coverage, English Markdown).
12. No Russian technical comments/docstrings introduced; user-facing Russian/Kazakh text stays in
    the localization/business-content layer.
