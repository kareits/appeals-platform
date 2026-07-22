# CONTEXT_LOADING_GUIDE — Context Loading per Task

What to read in each session. The goal is the minimum sufficient context, so Claude is not
overloaded and unrelated components are not changed (R-12).

**Always mandatory (any task):**
- root `CLAUDE.md` (language and documentation policy, ADR-015)
- `chatgpt_docs/CLAUDE.md` (architectural prohibitions, data ownership — read-only source)
- `chatgpt_docs/docs/00_MASTER_SPEC.md`
- `docs/DOCUMENT_PRECEDENCE.md`
- `docs/DECISION_LOG.md`
- the current task file from `tasks/DETAILED_TASK_INDEX.md` (the relevant subtask)
- the phase section of `docs/IMPLEMENTATION_PLAN.md` (Goal/API/Events/Data/Acceptance/Out-of-scope
  for the current EP; refines the subtask)

**Notation:** "must not change" = services out of scope; contracts change before implementation
(OpenAPI/JSON Schema + contract tests first).

**Language reminder (ADR-015):** all produced code, docstrings, comments, tests, OpenAPI/JSON
Schema descriptions, ADRs, and technical docs are in English; the conversation with the user stays
in Russian; user-facing Russian/Kazakh text goes to the localization/business-content layer.

---

## EP-0 · TASK_00A/B/C — Bootstrap

- Mandatory: `docs/03_ARCHITECTURE.md`, `docs/05_API_AND_EVENT_CONTRACTS.md`,
  `chatgpt_docs/tasks/TASK_00_REPOSITORY_BOOTSTRAP.md`.
- If needed: `contracts/README.md`.
- May change: monorepo skeleton, `libs/`, demo service, `infrastructure/`, CI (incl. docstring
  coverage and English-Markdown gates).
- Must not change: business services (not created at this stage).
- Session scope: one subtask (00A / 00B / 00C).

## EP-0F · TASK_00D — Flowable Spike

- Mandatory: `docs/04_FLOWABLE_PROCESS.md`, `services/PROCESS_ADAPTER.md`.
- If needed: EP-0 notes.
- May change: Process Adapter only (technical loop), test BPMN.
- Must not change: Ticket/Mailbox/Document/others.
- Scope: one spike (no business process).

## EP-1 · TASK_01A–E — Ticket & Manual Workflow

- Mandatory: `docs/01_REGULATORY_AND_BUSINESS_REQUIREMENTS.md`, `docs/02_DATA_DICTIONARY.md`, the
  affected service spec (`services/TICKET_SERVICE.md` / `IAM_SERVICE.md` / `BFF_SERVICE.md`).
- If needed: `docs/06_SECURITY_RETENTION_AUDIT.md` (audit, retention, RBAC), `docs/05` (ticket.*
  events).
- May change by subtask:
  - 01A–01C → Ticket Service;
  - 01D → IAM Service;
  - 01E-1 → BFF; 01E-2/3/4 → web-frontend.
- Must not change: Process Adapter, Mailbox, Document, Notification, Integration.
- Scope: one subtask (01A…01E-4).

## EP-2 · TASK_03A — Document Foundation

- Mandatory: `docs/02` (Document metadata), `services/DOCUMENT_SERVICE.md`, `docs/06`
  (attachments).
- If needed: `contracts/README.md`.
- May change: Document Service; `contracts/openapi/document-service.v1.yaml`.
- Must not change: Ticket/Mailbox/Process Adapter (only `document_id`/`ticket_id` are used).
- Scope: 03A-1 or 03A-2.

## EP-3 · TASK_02A–E — Flowable Integration

- Mandatory: `docs/04`, `services/PROCESS_ADAPTER.md`, `orchestration/README.md`; EP-0F notes.
- If needed: `docs/05` (process.* events), `services/TICKET_SERVICE.md` (projection consumer),
  `services/BFF_SERVICE.md` (task UI).
- May change by subtask:
  - 02A → `orchestration/` (BPMN/DMN);
  - 02B/02C/02D → Process Adapter (+ Ticket Service as projection consumer in 02D);
  - 02E → BFF/web-frontend.
- Must not change: Document/Mailbox/Integration.
- Scope: one subtask.

## EP-4 · TASK_03B — Document Hardening

- Mandatory: `services/DOCUMENT_SERVICE.md`, `docs/06`, `docs/07` (hashes/versions).
- May change: Document Service; extend its OpenAPI (no breaking changes).
- Must not change: other services.
- Scope: 03B-1 / 03B-2 / 03B-3.

## EP-5 · TASK_04A–D — Exchange Email

- Mandatory: `services/MAILBOX_SERVICE.md`, `docs/02` (mail message), `docs/06` (email).
- If needed: `services/DOCUMENT_SERVICE.md` (attachments), `services/PROCESS_ADAPTER.md`
  (reply/send), `docs/05` (mail.*/response.*).
- May change by subtask:
  - 04A → Mailbox (provider interface/Fake/EML);
  - 04B → Mailbox (+ Document/Ticket calls via API/events);
  - 04C → Mailbox (+ Process Adapter correlation);
  - 04D → Mailbox (+ Process Adapter handle email sent).
- Must not change: internals of Document/Ticket/Process (only their APIs).
- Scope: one subtask.

## EP-6 · TASK_05A–C — Reporting & Audit

- Mandatory: `docs/01` (reporting), `docs/02` (analytics), `services/TICKET_SERVICE.md`.
- If needed: `docs/06` (audit/exports), `services/BFF_SERVICE.md` (report endpoints).
- May change: Ticket Service (reporting/read-model module), BFF/frontend (reports).
- Must not change: other services; cross-service SQL and Flowable DB reads are forbidden (ADR-011).
- Scope: 05A / 05B / 05C.

## EP-7 · TASK_06A–E — Production Readiness

- Mandatory: `docs/06`, `chatgpt_docs/tasks/TASK_06_PRODUCTION_READINESS.md`.
- If needed: the affected service's spec; `docs/03` (reliability).
- May change by subtask:
  - 06A → IAM (OIDC);
  - 06B → all (config/secrets/TLS) — targeted;
  - 06C → infrastructure (backup/restore);
  - 06D → observability/DLQ/dashboard/indexes;
  - 06E → tests and documentation.
- Scope: one subtask; avoid changing many services at once.

---

## General session-scope rules

- One subtask from the index per session.
- A limited set of changeable services (lists above).
- Contracts first (OpenAPI/JSON Schema + contract tests), then implementation.
- Completion: acceptance criteria + tests + migrations (migration/backfill/rollback/validation) +
  documentation update, including the ADR-015 Definition-of-Done items (English docstrings/comments,
  updated OpenAPI/event descriptions, README/SERVICE_MAP, passing documentation CI checks).
- Do not read the whole set — only the mandatory + "if needed" documents for the phase.
