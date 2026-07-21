# DETAILED_TASK_INDEX — Session Subtask Index

Decomposition of the large `chatgpt_docs/tasks/TASK_00–06` into subtasks sized for one Claude
session. The source `chatgpt_docs/tasks/TASK_*` files are **not modified**; this index is the
source of truth for the decomposition (see [DOCUMENT_PRECEDENCE.md](../docs/DOCUMENT_PRECEDENCE.md)).

**Each subtask:** fits one session; a limited set of changeable services; a verifiable result;
does not depend on non-existent corporate access (uses fakes/mocks); ends with tests and a
documentation update.

**Definition of Done (all subtasks):** acceptance criteria met; tests pass; migrations verified
(M/B/R/V); OpenAPI/events current and passing contract tests; no cross-service DB dependencies;
security check; Docker build + health + compose smoke; **English docstrings on every new/modified
module/class/function/method; English "why" comments for non-obvious behavior; updated
OpenAPI/event descriptions; updated service `README.md`/`SERVICE_MAP.md` where behavior changed;
documentation CI checks pass (docstring coverage, English Markdown); no Russian technical
docstrings/comments** (ADR-015, root `CLAUDE.md`).

**Attributes:** EP (execution phase, independent of the TASK number) · Origin (source TASK) ·
Services · Dependencies · Data (M/B/R/V = migration/backfill/rollback/validation) · DoD-specific ·
Independent check.

Execution order (ADR-005):
`00A→00B→00C→00D→01A→01B→01C→01D→01E-1..4→03A-1→03A-2→02A→02B-1..3→02C-1..3→02D→02E-1..3→03B-1..3→04A→04B-1..3→04C→04D→05A→05B→05C→06A→06B→06C→06D→06E-1..3`.

---

## EP-0 — Bootstrap (Origin: TASK_00)

### 00A — Monorepo skeleton + shared library + demo service
- Services: skeleton, `libs/`, demo service + template. Dependencies: —.
- Data: M sample migration for the demo service; R downgrade; V apply/rollback in CI. (B — none.)
- DoD-specific: directories `apps/services/orchestration/contracts/infrastructure/libs`; `libs`
  (observability/http/testing, ADR-007); demo service with health; service template; Ruff `D`
  rules + docstring-coverage tool + English-Markdown check configured; **no scaffolding of other
  services** (ADR-013); ADR-SHARED-LIBS and the language-policy ADR drafted.
- Check: demo service starts locally; `libs` imports; lint/type/test and documentation gates pass.

### 00B — Docker Compose infrastructure + health
- Services: infrastructure. Dependencies: 00A.
- Data: — (besides the existing sample migration).
- DoD-specific: compose with PostgreSQL, RabbitMQ, Flowable, reverse proxy; `.env.example`;
  Makefile up/down/test/lint/migrate; Flowable only on dev/private network.
- Check: `docker compose up --build` starts; `/health/live`,`/health/ready` available; no secrets.

### 00C — CI + lint/type/test + event-envelope schema
- Services: CI, contracts. Dependencies: 00A, 00B.
- Data: —.
- DoD-specific: CI runs lint (Ruff incl. `D`) / type (Pyright/mypy) / test (pytest) + docstring
  coverage + English-Markdown; `contracts/events/event-envelope.v1.json`; compose smoke in CI;
  ADR-EVENT-CATALOG recorded.
- Check: CI green; schema validates; envelope has all fields (`eventId…payload`).

### 00D — Flowable Spike (Origin: TASK_00, technical) · EP-0F
- Services: Process Adapter (technical). Dependencies: 00B.
- Data: — (uses the Flowable DB).
- DoD-specific: from FastAPI reproduce start process → user task → claim → complete → timer
  (accelerated) → message correlation → history; **no business process**; pattern documented for
  EP-3.
- Check: integration test against Flowable in compose; idempotent start by business key.

---

## EP-1 — Ticket & Manual Workflow (Origin: TASK_01)

### 01A — Ticket model + migrations + registration number
- Services: Ticket Service. Dependencies: 00C.
- Data: M Ticket/applicant/representative tables; B seed dictionaries (draft codes, Q-A1); R
  downgrade + no deletion of regulatory data; V unique registration number, required/nullable
  conditional fields.
- DoD-specific: model per `docs/02`; business number separate from UUID; optimistic locking
  (`version`).
- Check: unit invariant tests; migration applies/rolls back.

### 01B — Create/update/classify/comments/search
- Services: Ticket Service. Dependencies: 01A.
- Data: M search indexes; V search filters.
- DoD-specific: use cases CreateManualTicket/UpdateTicketDetails/ClassifyTicket/AddComment; search
  by number/IIN-BIN/name/contract/status/stage/product/classifier/channel/assignee/team/dates.
  Events `ticket.created.v1`,`ticket.classified.v1`,`ticket.updated.v1` via Outbox.
- Check: integration registration→search; events published.

### 01C — Decision + close validation + retention + audit + SLA due_at
- Services: Ticket Service. Dependencies: 01B.
- Data: M decision/closure/retention fields + audit table; V close blocked without decision,
  retention on close.
- DoD-specific: RecordDecision; close requires decision+closure reason+dates;
  `retention_until`/`legal_hold`; SLA policy + business calendar → `internal_due_at`/`legal_due_at`
  (ADR-009, temporary calendar Q-C1); events `ticket.decision_recorded.v1`,`ticket.closed.v1`.
- Check: regulatory tests (close blocked without decision, retention); due_at computation test.

### 01D — IAM dev-users/roles + authorization matrix
- Services: IAM Service. Dependencies: 00C (parallel to 01A–C).
- Data: M users/roles/teams; B seed roles/users; V role checks.
- DoD-specific: dev/local auth (non-production only); 7 roles; permission claims; role changes
  audited; password hashing for temporary auth.
- Check: unit authorization; first-line read-only enforced at the permission level.

### 01E-1 — BFF (auth context, workspace aggregation, error normalization)
- Services: BFF. Dependencies: 01C, 01D.
- Data: M own BFF schema (if needed); V partial read failures flagged.
- DoD-specific: auth context; workspace aggregation (ticket card + placeholders for
  process/mail/documents in EP-1); RFC7807; correlation ID.
- Check: integration BFF↔Ticket/IAM; error normalization.

### 01E-2 — Frontend: login + ticket list/search
- Services: web-frontend. Dependencies: 01E-1.
- Data: —.
- DoD-specific: dev-login; appeal list; search/filter from UI. UI text in the localization layer
  (Russian/Kazakh allowed, ADR-015).
- Check: manual run + list/search component tests.

### 01E-3 — Frontend: manual-registration form
- Services: web-frontend. Dependencies: 01E-2.
- Data: —.
- DoD-specific: manual-registration form for any written appeal; required validated, conditionals
  nullable.
- Check: registration creates a ticket with a unique number.

### 01E-4 — Frontend: card + comments + decision/close
- Services: web-frontend. Dependencies: 01E-3.
- Data: —.
- DoD-specific: appeal card; comments; decision recording; close with validation; first-line
  read-only in UI.
- Check: E2E "registration→decision→close" (placeholder status).

---

## EP-2 — Document Foundation (Origin: TASK_03A)

### 03A-1 — Metadata + FileStorage + local + upload/download/list + link
- Services: Document Service. Dependencies: 01A (ticket_id), 00C.
- Data: M document metadata; R downgrade without deleting files; V no path traversal, random
  storage key.
- DoD-specific: `FileStorage` protocol; `LocalFileStorage`; upload/stream/list; `document_id↔
  ticket_id` link; persistent volume; `storage_backend=local`; `contracts/openapi/document-service.v1.yaml`.
- Check: integration upload→list→download; restart does not lose files.

### 03A-2 — Hash + MIME/size + mock scan + contract tests
- Services: Document Service. Dependencies: 03A-1.
- Data: M hash/scan_status fields; V hash verified, pending inaccessible.
- DoD-specific: SHA-256; MIME validation; size limits; mock scan (→CLEAN/AVAILABLE); events
  `document.uploaded.v1`,`document.available.v1`; no binary in RabbitMQ; contract tests.
- Check: contract tests; pending/infected inaccessible; hash verified.

---

## EP-3 — Flowable Integration (Origin: TASK_02)

### 02A — BPMN + DMN v1
- Services: orchestration. Dependencies: 00D, 03A-2.
- Data: BPMN/DMN in Git (versioned deployment).
- DoD-specific: `appeal_restructuring_v1.bpmn20.xml`; `appeal_routing_v1.dmn` (inputs/outputs per
  `docs/04`, output `required_document_ruleset`); completeness as a human task (ADR-010);
  `PROCESS_CHANGELOG.md`.
- Check: test process scenarios; DMN yields team/priority/sla/approval/ruleset.

### 02B-1 — Process Adapter skeleton + Flowable client + start_process
- Services: Process Adapter. Dependencies: 02A.
- Data: M ticket/process mapping + idempotency; V one ticket→one process (business key).
- DoD-specific: StartAppealProcess on `ticket.created.v1`; mapping; idempotency;
  `contracts/openapi/process-adapter.v1.yaml`.
- Check: duplicate start protected by business key.

### 02B-2 — List work items + claim/unclaim
- Services: Process Adapter. Dependencies: 02B-1.
- Data: M task mapping.
- DoD-specific: ListWorkItems, ClaimTask/unclaim; task command authorization.
- Check: integration list/claim; repeated claim safe.

### 02B-3 — Complete_task + reassign + authorization
- Services: Process Adapter. Dependencies: 02B-2.
- Data: —.
- DoD-specific: CompleteTask, ReassignTask; authorized completion; actions audited; no full
  documents in variables.
- Check: authorized completion; reassign preserves history/permissions.

### 02C-1 — WAITING timer(5d) + customer reply correlation
- Services: Process Adapter, orchestration. Dependencies: 02B-3.
- Data: —.
- DoD-specific: WAITING_FOR_CUSTOMER; 5-day timer; message event on customer reply;
  timeout→reminder-or-close (Q-C2, temporarily reminder+task).
- Check: accelerated timer test; reply correlation advances the stage.

### 02C-2 — HOLD timer(15d) + reason + resume
- Services: Process Adapter, orchestration. Dependencies: 02C-1.
- Data: —.
- DoD-specific: ON_HOLD with mandatory reason; 15-day timer; notification; resume returns to the
  previous stage.
- Check: reason mandatory; accelerated timer; resume.

### 02C-3 — Approval branch
- Services: Process Adapter, orchestration. Dependencies: 02C-2.
- Data: —.
- DoD-specific: supervisor approval branch by `approval_policy` (Q-C3); link to ResponseDraft
  approval status (ADR-008).
- Check: approval required/not required per DMN.

### 02D — Projection events + process audit
- Services: Process Adapter (producer), Ticket Service (consumer). Dependencies: 02C-3.
- Data: M projection outbox (Adapter) + projection update (Ticket); V idempotency, eventual
  consistency.
- DoD-specific: `process.started/task_created/assignment_changed/status_changed/completed.v1`;
  `ticket.deadline_breached.v1`; Ticket updates the projection; status changes only via
  projection; SLA: Ticket computes due_at, Flowable sets the timer (ADR-009).
- Check: projection converges; duplicate events safe; no direct status editing; email response
  does not close.

### 02E-1 — UI: task list/queues
- Services: BFF/web-frontend. Dependencies: 02D.
- DoD-specific: work-task list and queues.
- Check: tasks visible per roles/teams.

### 02E-2 — UI: claim/complete/reassign
- Services: BFF/web-frontend. Dependencies: 02E-1.
- DoD-specific: claim/complete/reassign actions from UI via BFF (`/tasks/{id}/complete`,
  `/reassign`).
- Check: E2E task assignment/completion.

### 02E-3 — UI: SLA/deadlines + hold/resume
- Services: BFF/web-frontend. Dependencies: 02E-2.
- DoD-specific: SLA/deadline indicators; hold with reason / resume from UI.
- Check: breach display; hold/resume works.

---

## EP-4 — Document Hardening (Origin: TASK_03B)

### 03B-1 — Versions + preview
- Services: Document Service. Dependencies: 03A-2, 02D.
- Data: M version field; B `version=1` for existing; V versions preserved.
- DoD-specific: AddVersion; safe preview; OpenAPI extension without breaking changes.
- Check: versions not lost; preview safe.

### 03B-2 — Antivirus + download audit + soft delete
- Services: Document Service. Dependencies: 03B-1.
- Data: M scan/deleted_at fields + download audit; V INFECTED/PENDING inaccessible, soft delete≠purge.
- DoD-specific: scanner interface + integration (mock→real, Q-B6); states UPLOADING…INFECTED/DELETED;
  download audit; soft delete; events `document.scan_failed.v1`,`document.deleted.v1`.
- Check: infected inaccessible; download audit written.

### 03B-3 — Cleanup jobs + GridFS readiness
- Services: Document Service. Dependencies: 03B-2.
- Data: M migrated_at field; V API unchanged when adding a backend.
- DoD-specific: cleanup jobs; dual-read readiness; unchanged `document_id`; ADR-STORAGE-MIGRATION.
- Check: a GridFS backend can be added without API change.

---

## EP-5 — Exchange Email (Origin: TASK_04)

### 04A — Provider interface + FakeMailboxProvider + EML fixtures
- Services: Mailbox Service. Dependencies: 03A-2, 02D.
- Data: M Mailbox schema (checkpoints, dedup, attempts).
- DoD-specific: provider methods (subscribe/poll, list since checkpoint, get body/attachments,
  send, delivery status, save checkpoint); `FakeMailboxProvider`; EML fixtures; outbound capture;
  `contracts/openapi/mailbox-service.v1.yaml`.
- Check: fixtures read; interface covered by unit tests.

### 04B-1 — Poll/checkpoint + dedup
- Services: Mailbox Service. Dependencies: 04A.
- Data: V duplicate external/internet message ID ignored.
- DoD-specific: poll with checkpoint; deduplication.
- Check: duplicate not reprocessed.

### 04B-2 — Body + attachments via Document Service
- Services: Mailbox Service (+ Document API). Dependencies: 04B-1.
- Data: M mail↔document link.
- DoD-specific: body html/text; optional raw EML; attachments stored via Document Service (by ID).
- Check: attachments linked; no direct file paths.

### 04B-3 — Ticket creation from mail + mail.received
- Services: Mailbox Service (+ Ticket via event). Dependencies: 04B-2.
- Data: V one fixture→one ticket.
- DoD-specific: `mail.received.v1`; CreateTicketFromMail; ticket number in subject.
- Check: fixture creates one ticket with attachments.

### 04C — Reply linking + reconciliation
- Services: Mailbox Service (+ Process Adapter correlation). Dependencies: 04B-3.
- Data: —.
- DoD-specific: reply linking (conversation/in-reply-to/references); `mail.linked.v1`;
  reconciliation; correlate customer reply into the process.
- Check: reply linked to the ticket; reply correlation advances the stage.

### 04D — Outbound send + idempotency + attempts
- Services: Mailbox Service (+ Process Adapter handle email sent). Dependencies: 04C.
- Data: M delivery attempts; V approved-only, verified recipient, sent once.
- DoD-specific: send only approved (Flowable authorization, ADR-008); fixed sender; documents by
  ID; idempotency; delivery attempts;
  `mail.send_requested.v1`,`mail.sent.v1`,`mail.send_failed.v1`; `response.*`; header-injection
  protection. **No `email.*`/`response.returned`** (ADR-006).
- Check: approved response sent once; failure retries and is visible; full timeline.

---

## EP-6 — Reporting & Audit (Origin: TASK_05)

### 05A — Read-model module + event subscription
- Services: Ticket Service (reporting module). Dependencies: 02D, 04D.
- Data: M read-model + analytics tables (SystemicIssue/CorrectiveAction/Satisfaction); B replay
  from event history; R downgrade the read-model (source events preserved); V overdue reproducible.
- DoD-specific: subscribe to `ticket.*`,`process.*`,`mail.*`,`response.*`; **no cross-service SQL
  and no Flowable DB reads** (ADR-011).
- Check: read-model built from events; replay reproduces state.

### 05B — Reports + filters
- Services: Ticket Service, BFF/frontend. Dependencies: 05A.
- Data: —.
- DoD-specific: counts/classification by product; deadlines/compliance; satisfaction; systemic
  issues/actions; backlog aging; workload; `GET /reports/...`.
- Check: filters apply to reports; overdue reproducible; classifier history retained.

### 05C — XLSX/CSV export + audit
- Services: Ticket Service, BFF/frontend. Dependencies: 05B.
- Data: V exports audited.
- DoD-specific: XLSX/CSV export; filters apply to exports; exports audited; physical deletion
  unavailable.
- Check: export with filters; audit record written; physical-deletion attempt rejected.

---

## EP-7 — Production Readiness (Origin: TASK_06)

### 06A — OIDC adapter
- Services: IAM. Dependencies: 05C (and the whole platform).
- Data: —.
- DoD-specific: OIDC adapter (Q-B3); dev auth disabled in production.
- Check: no dev-auth in production; login via OIDC (or mock IdP).

### 06B — Secrets/TLS/production config
- Services: all (targeted). Dependencies: 06A.
- Data: —.
- DoD-specific: secrets integration; TLS; production config; user/service credential separation.
- Check: least privilege verified; no secrets in the repository.

### 06C — Backup/restore + RPO/RTO
- Services: infrastructure. Dependencies: 06B.
- Data: V consistent restore of PG+file volume+Flowable DB.
- DoD-specific: backup/restore procedures; RPO/RTO recorded (Q-B5); restore drill.
- Check: restore demonstrated; RPO/RTO recorded.

### 06D — Observability + DLQ + reconciliation dashboard + indexes
- Services: all/infrastructure. Dependencies: 06C.
- Data: M performance indexes; R downgrade indexes.
- DoD-specific: logs/metrics/alerts; DLQ; reconciliation dashboard; indexes; dependencies
  monitored.
- Check: outbox prevents event loss; Exchange reconciliation prevents loss; DLQ works.

### 06E-1 — Load tests
- Services: tests. Dependencies: 06D.
- DoD-specific: load scenarios for key flows.
- Check: target metrics achieved/recorded.

### 06E-2 — Security tests
- Services: tests. Dependencies: 06E-1.
- DoD-specific: security tests (auth, traversal, injection, PII, exports).
- Check: no critical vulnerabilities.

### 06E-3 — Runbooks + user docs + retention dry-run
- Services: documentation. Dependencies: 06E-2.
- Data: V retention dry-run without real deletion.
- DoD-specific: runbooks; user docs; retention dry run.
- Check: dry-run report with no deletion; documentation ready for the pilot.

---

## Subtask-to-source TASK mapping

| Origin TASK (chatgpt_docs) | Subtasks | EP |
|---|---|---|
| TASK_00_REPOSITORY_BOOTSTRAP | 00A, 00B, 00C, 00D | EP-0, EP-0F |
| TASK_01_TICKET_AND_MANUAL_WORKFLOW | 01A, 01B, 01C, 01D, 01E-1..4 | EP-1 |
| TASK_03_DOCUMENTS → **03A** (Foundation) | 03A-1, 03A-2 | EP-2 |
| TASK_02_FLOWABLE_INTEGRATION | 02A, 02B-1..3, 02C-1..3, 02D, 02E-1..3 | EP-3 |
| TASK_03_DOCUMENTS → **03B** (Hardening) | 03B-1, 03B-2, 03B-3 | EP-4 |
| TASK_04_EXCHANGE_EMAIL | 04A, 04B-1..3, 04C, 04D | EP-5 |
| TASK_05_REPORTING_AND_AUDIT | 05A, 05B, 05C | EP-6 |
| TASK_06_PRODUCTION_READINESS | 06A, 06B, 06C, 06D, 06E-1..3 | EP-7 |

Note: the original `TASK_03_DOCUMENTS` is split into 03A/03B (ADR-005); the execution order places
03A before TASK_02 and 03B after it.
