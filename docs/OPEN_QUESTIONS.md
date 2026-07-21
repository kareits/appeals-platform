# OPEN_QUESTIONS — Open Questions

For each question: importance, the phase by which an answer is needed, and a safe temporary
assumption (so development is not blocked).
Addressees: **IT**, **Business**, **Legal/Compliance**, **InfoSec**.

---

## A. Blocking the start of development

_No questions fully block the start._ EP-0/EP-1 are feasible on dev-auth and mocks. Below are
questions worth clarifying early, each with a safe assumption.

| ID | Question | Addressee | Needed by | Why it matters | Temporary assumption |
|---|---|---|---|---|---|
| Q-A1 | Approved taxonomy of classifiers, products, and closure reasons (codes and values) | Business | EP-1 | Drives dictionaries, DMN routing, and reporting | Seed fixtures with temporary codes; map later |
| Q-A2 | Role permission matrix (EMPLOYEE/SUPERVISOR/FIRST_LINE_READONLY/OMBUDSMAN/ANALYST/ADMIN/AUDITOR) by action | Business/InfoSec | EP-1 | Authorization matrix in IAM/BFF | Conservative matrix from `docs/00`/`docs/06`, refine later |

## B. Blocking production (do not block MVP on mocks)

| ID | Question | Addressee | Needed by | Why it matters | Temporary assumption |
|---|---|---|---|---|---|
| Q-B1 | Exchange type (on-prem/O365), shared mailbox, available API (Graph/EWS/IMAP), auth method | IT | EP-5 (real adapter), mandatory by EP-7 | Defines the real Mailbox adapter | `FakeMailboxProvider` + EML fixtures |
| Q-B2 | Test mailbox and send permissions from the fixed sender | IT/InfoSec | EP-5/EP-7 | Test receive/send without risk to the live mailbox | Outbound capture (no real sending) |
| Q-B3 | OIDC provider (AD/Entra), client credentials, group→role mapping | IT/InfoSec | EP-7 | Replacing dev-auth | dev-auth non-production only |
| Q-B4 | Accounting-system contract (lookup by IIN, contracts, debt, prior restructurings) | IT | EP-3/EP-7 (as needed) | Enriching client/contract card | `FakeCoreSystemAdapter` + manual entry |
| Q-B5 | RPO/RTO and the consistent backup/restore procedure (PG + file volume + Flowable DB) | IT/InfoSec | EP-7 | Integrity of regulatory-data restore | Define default RPO/RTO, confirm with IT |
| Q-B6 | Antivirus engine choice and quarantine mode | InfoSec/IT | EP-4/EP-7 | Real attachment scanning | Scanner interface + mock status |
| Q-B7 | PII storage requirements (masking, encryption, KZ data localization) | Legal/Compliance/InfoSec | EP-7 | Compliance with PII law | IIN/BIN masking, TLS, backup encryption per `docs/06` |

## C. Not blocking MVP

| ID | Question | Addressee | Needed by | Why it matters | Temporary assumption |
|---|---|---|---|---|---|
| Q-C1 | Exact SLA business calendars (working hours, KZ holidays, separate internal/regulatory deadline) | Business/Legal | EP-3 (refine), pilot | Correct due_at and timer computation | Calendar days without holidays; SLA params from `docs/01` |
| Q-C2 | Escalation rules on WAITING(5d)/HOLD(15d) timeout: reminder vs close, who is notified | Business | EP-3 | The reminder-or-close BPMN branch | reminder + task to the employee, no auto-close |
| Q-C3 | Approval policy (when supervisor approval is required) | Business | EP-3 | DMN `approval_policy` | Approval for refusals/disputed decisions |
| Q-C4 | Response form and text: PDF template, requisites, outgoing number | Business/Legal | EP-3/EP-5 | Preparing and sending the response | The employee uploads a ready PDF |
| Q-C5 | Satisfaction metric (survey version, channel, scale) | Business | EP-6 | Satisfaction reporting | `Satisfaction` fields from `docs/02`, simple scale |
| Q-C6 | Composition and periodicity of mandatory management reporting/exports | Business/Compliance | EP-6 | Set of reports and exports | Reports from `docs/01` (counts/deadlines/satisfaction/systemic) |
| Q-C7 | Document-type catalog (`document_type_code`) and required rulesets by classifier | Business | EP-2/EP-3 | DMN required document codes, human completeness | Basic type set; ruleset refined later |

## D. InfoSec questions

| ID | Question | Addressee | Needed by | Why it matters | Temporary assumption |
|---|---|---|---|---|---|
| Q-D1 | Audit policy: event list, audit retention period, export access | InfoSec/Compliance | EP-1/EP-6 | Completeness and protection of the audit log | Audit per `docs/06` (logins/views/changes/exports/…) |
| Q-D2 | MIME allowlist and attachment size limits | InfoSec | EP-2 | File-upload protection | Conservative allowlist + reasonable limits |
| Q-D3 | Masking policy and access rules for full identifiers | InfoSec/Legal | EP-1/EP-6 | PII protection in UI/exports/logs | Masking by default, full access by permission |
| Q-D4 | Separation of user/service credentials and least privilege per service | InfoSec/IT | EP-7 | Production access model | Separate DB users per service (already in MVP) |

## E. Questions arising from spec conflicts (resolved by ADR, need confirmation)

| ID | Question | Resolution | Confirmation needed from |
|---|---|---|---|
| Q-E1 | Unified event naming (`email.*` vs `mail.*`, `deadline.*` vs `ticket.deadline_*`, `response.returned`) | Canonicalize `mail/ticket/response` (ADR-006), single event catalog in EP-0C | Technical contracts owner |
| Q-E2 | Ownership of the "response" entity (draft/approve/send) | ADR-008 (Ticket/Document/Mailbox/Flowable) | Business/architecture |
| Q-E3 | Where SLA deadlines are computed and timers set | ADR-009 (Ticket computes, Flowable sets timer, Notification notifies) | Business (params), architecture |
| Q-E4 | How reporting is built without cross-service SQL | ADR-011 (read-model in Ticket Service from events) | Architecture |
| Q-E5 | Language policy for code and documentation | ADR-015 (English technical artifacts; Russian conversation and business content) | Team lead / stakeholders |
