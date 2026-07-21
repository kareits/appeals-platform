# PROJECT_ROADMAP — Solva Appeals Platform Roadmap

## Project goal

An internal MFO platform for registering, processing, controlling, analyzing, and storing all
written appeals from consumers of financial services. ~99% of appeals concern microcredit
restructuring and arrive at `dolg@solva.kz`. Data is retained for at least 5 years; an ordinary
user cannot physically delete an appeal or a document.

## MVP scope

**In scope:** temporary dev-auth + OIDC readiness; manual registration; a provider interface to
Exchange (connected after access is granted); the register and the card; classifiers; Flowable
BPMN/DMN; assignment/reassignment; statuses, stages, SLA, and timers; Document Service;
local/network file storage; sending responses via Mailbox; reporting and audit; 5-year retention;
AI-ready contracts.

**Out of scope:** MongoDB/GridFS, WhatsApp/Telegram, CMMN, Kubernetes, Windmill, autonomous AI
decisions, real OCR/LLM, automatic restructuring decisions.

## Key architectural decisions

Full list — see [DECISION_LOG.md](DECISION_LOG.md); document precedence — see
[DOCUMENT_PRECEDENCE.md](DOCUMENT_PRECEDENCE.md).

- Monorepo, coarse-grained microservices, separate DB per service, no cross-service DB
  (ADR-001,002,004).
- Stack: Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2 / Alembic / PostgreSQL / RabbitMQ /
  Flowable / React+TS / Docker Compose (ADR-003).
- Reorder: `TASK_00 → 01 → 03A → 02 → 03B → 04 → 05 → 06` (ADR-005).
- Canonical events `mail.*` / `ticket.*` / `response.*` / `process.*` / `document.*` /
  `notification.*` (ADR-006).
- Shared libraries limited to observability/http/testing (ADR-007).
- Ownership: ResponseDraft (ADR-008), SLA/business calendar (ADR-009), completeness check as a
  human task (ADR-010), reporting as a read-model in Ticket Service (ADR-011).
- Mocks for Exchange/SSO/core (ADR-012). Bootstrap without scaffolding all services (ADR-013).
  File storage local→GridFS (ADR-014).
- **English-only technical code and documentation; conversation with the user in Russian**
  (ADR-015).

## Execution phases

An execution phase (EP) is a roadmap unit independent of the origin TASK number.

| EP | Origin | Name | Expected result |
|---|---|---|---|
| EP-0 | TASK_00A–C | Bootstrap | Monorepo, demo service + template, compose (PG/RabbitMQ/Flowable/proxy), health, shared library, event-envelope schema, CI, documentation quality gates |
| EP-0F | TASK_00D | Flowable Spike | Technical Process Adapter↔Flowable loop: start/user task/claim/complete/timer/message correlation/history — no business process |
| EP-1 | TASK_01 | Ticket + Manual Workflow | Vertical slice: manual registration → card → classification → decision → close (placeholder status); dev-auth; SLA due_at |
| EP-2 | TASK_03A | Document Foundation | Minimal Document Service: metadata, local storage, upload/download/list, link, hash, MIME/size, mock scan |
| EP-3 | TASK_02 | Flowable Integration | BPMN/DMN v1, Process Adapter, real workflow instead of placeholder; WAITING/HOLD timers; approval; projection events |
| EP-4 | TASK_03B | Document Hardening | Versions, preview, antivirus, download audit, soft delete, cleanup jobs, GridFS readiness |
| EP-5 | TASK_04 | Exchange Email | Provider abstraction, Fake+EML, receive/dedup/attachments/reply linking/send/reconciliation |
| EP-6 | TASK_05 | Reporting & Audit | Read-model in Ticket Service, mandatory reporting, analytics, XLSX/CSV export, full audit |
| EP-7 | TASK_06 | Production Readiness | OIDC, secrets, TLS, backup/restore, RPO/RTO, observability, DLQ, retention dry-run, runbooks |

## Dependencies between phases

```
EP-0 ──> EP-0F (spike, de-risks Flowable before EP-3)
EP-0 ──> EP-1 ──> EP-2 ──> EP-3 ──> EP-4 ──> EP-5 ──> EP-6 ──> EP-7
                   │                          ▲
                   └── EP-2 (Documents) needed by EP-3 and EP-5 ─┘
```

- EP-1 depends on EP-0 (infrastructure, library, IAM dev-auth).
- EP-2 (Document Foundation) is required before EP-3 (BPMN uses completeness) and before EP-5
  (Mailbox uploads attachments via Document Service).
- EP-3 depends on EP-1 (card/projection) and EP-0F (validated Flowable loop).
- EP-5 depends on EP-2 (attachments) and EP-3 (process, reply correlation, response sending).
- EP-6 depends on EP-1..EP-5 (report data via events).
- EP-7 depends on all previous phases.

Detailed matrix — see [DEPENDENCY_MAP.md](DEPENDENCY_MAP.md).

## Phase transition criteria

Transition to the next phase is allowed when the current phase satisfies:

- the phase acceptance criteria (see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md));
- tests added and passing (unit/integration/contract, as applicable);
- migrations verified (migration/backfill/rollback/validation for data changes);
- OpenAPI/events current and passing contract tests;
- documentation updated (English technical docs; docstring/comment and English-Markdown checks
  pass in CI per ADR-015);
- no cross-service DB dependencies;
- security check performed;
- `docker compose up --build` + health smoke test pass.

## Milestones with a working result

- **After EP-1:** an appeal can be registered manually, the card maintained, a decision recorded,
  and the ticket closed — the end-to-end regulatory minimum without Flowable.
- **After EP-3:** a real BPMN process with assignments, timers, and approval.
- **After EP-5:** mail receiving and sending via the Fake provider, full timeline.
- **After EP-6:** mandatory management reporting and audit.
- **After EP-7:** pilot readiness.

## Risks (summary)

Full register — [RISK_REGISTER.md](RISK_REGISTER.md). Key risks: Exchange uncertainty, corporate
authentication, the Flowable learning curve, KZ SLA/business calendars, file storage and
migration, PII and retention, backup RPO/RTO, single developer vs microservice complexity, Claude
context, future OCR quality (ru/kz, handwriting), external AI providers.

## Deferred features (post-MVP)

MongoDB/GridFS file migration; corporate Document API; WhatsApp/Telegram channels; CMMN;
Kubernetes; a separate reporting service; real OIDC group sync; a full production antivirus
integration.

## AI development plan after MVP

AI is out of the MVP critical path; MVP implements only AI-ready artifacts (hashes, versions,
document types, manual completeness, response-draft history, feature flags, future schemas/events,
disabled AI service-task points).

**Development queue (post-MVP):**

1. **Document Intelligence Service** — digital-PDF text extraction; document classification;
   missing-document check (`required − detected = missing`); confidence and review artifacts.
2. **OCR** — printed Russian/Kazakh; experimental handwriting (untrusted by default).
3. **AI Assistant Service** — field extraction, summaries, response drafts, template selection,
   rule-compliance checks, source references; provider adapters.
4. **Human-in-the-loop levels:** (1) recommendation only; (2) send after employee approval; (3)
   controlled auto-send only for allowlisted low-risk scenarios.

**AI invariants (immutable):** AI does not decide restructuring, change a contract, close a
ticket, choose an arbitrary recipient, or send a legally significant refusal; AI receives no
Exchange/DB credentials; documents are untrusted; sending is authorized only by Flowable; AI
output is stored separately from confirmed data.
