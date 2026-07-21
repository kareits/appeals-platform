# RISK_REGISTER — Risk Register

Probability / impact: L (low) · M (medium) · H (high). Phase — execution phase from
[PROJECT_ROADMAP.md](PROJECT_ROADMAP.md).

| ID | Description | Prob. | Impact | Phase | Mitigation | Fallback | Trigger indicator |
|---|---|---|---|---|---|---|---|
| R-01 | **Exchange uncertainty** (type, shared mailbox, API, auth, sender permissions) | H | H | EP-5 | Provider interface + `FakeMailboxProvider` + EML fixtures; clarify params before the real adapter (ADR-012) | Work on the Fake provider; manual registration channel | By EP-5 no confirmed Exchange params / no test mailbox |
| R-02 | **Corporate authentication (OIDC/SSO)** unavailable in time | M | H | EP-7 | IAM interface + dev-auth (non-prod only); OIDC adapter deferred to EP-7 (ADR-012) | Pilot on limited auth without going to prod | By EP-7 no client credentials / group mapping from IT |
| R-03 | **Flowable learning curve** (BPMN/DMN, timers, correlation) | H | H | EP-0F/EP-3 | Early technical spike EP-0F before the business process; Process Adapter isolates Flowable | Simplified BPMN v1; move some logic into user tasks | EP-0F fails to reproduce start→timer→message→history |
| R-04 | **KZ SLA and business calendars** (working hours, holidays, separate internal/regulatory deadline) | M | H | EP-1/EP-3 | Versioned SLA policy + calendar module in Ticket Service (ADR-009); due_at computation tests | Fixed calendar days without holidays (temporary assumption) | Computed deadlines diverge from regulatory requirements |
| R-05 | **File storage** (volume loss, access, path traversal) | M | H | EP-2/EP-4 | `FileStorage` protocol, random key, hash verify, persistent volume, MIME/size, scan states | Restore from backup; block untrusted files | Restart loses files / pending-infected file accessible |
| R-06 | **Later MongoDB/GridFS migration** breaks API/links | L | M | post-MVP | Stable `document_id`, dual-read, background migration (ADR-014); API unchanged | Stay on local/network storage | API changes when adding the GridFS backend |
| R-07 | **Personal data** (IIN/BIN leak, logs, exports) | M | H | cross-cutting | Masking, no full IDs in logs, TLS, controlled exports, view/download audit | Restrict exports; tighten RBAC | Full identifier found in logs/export |
| R-08 | **Retention (5 years)** violated by premature deletion | L | H | cross-cutting | `retention_until`, `legal_hold`, soft delete ≠ purge, purge is a privileged job with audit | Restore from backup; block purge | An ordinary action physically deletes an appeal/document |
| R-09 | **Backup** inconsistent (PG / file volume / Flowable DB) | M | H | EP-7 | Consistent backup of the three stores; define and test RPO/RTO | Manual time-based reconciliation of restore | Restore does not reproduce a consistent state |
| R-10 | **Single developer** — throughput, bus factor | H | M | cross-cutting | Small session-sized tasks, minimal parallelism, decision documentation | Move deadlines; reduce MVP scope | Tasks do not fit a session; WIP grows |
| R-11 | **Microservice complexity** for one developer | M | M | cross-cutting | Coarse-grained boundaries, shared libs (observability/http/testing), no premature infrastructure | Merge services if proven redundant (via ADR) | Duplication, contract drift, slow changes |
| R-12 | **Claude context** — overload, changing unrelated components | M | M | cross-cutting | CONTEXT_LOADING_GUIDE, limited session scope, ban on editing other services | Split the task; restart with a narrow context | Edits outside the allowed service set |
| R-13 | **Future OCR quality** (printed ru/kz) | M | M | post-MVP | AI out of the MVP critical path; human-in-the-loop; confidence + review | Manual field entry | Low extraction accuracy on pilot documents |
| R-14 | **Handwriting** — unreliable recognition | H | M | post-MVP | Handwriting treated as untrusted; mandatory human verification | Fully manual handwriting processing | Untrusted handwriting used in a decision |
| R-15 | **External AI providers** (access, PII, cost, dependency) | M | M | post-MVP | Provider adapters; documents untrusted; narrow tool schemas; recipient not from the model | Disable AI features via feature flags | Provider unavailable / PII requirements not met |
| R-16 | **Event-contract inconsistency** (naming across documents) | M | M | EP-3/EP-5 | Canonicalize `mail/ticket/response` (ADR-006); single event catalog + schema tests in EP-0C | Reject non-canonical names in contract tests | A contract test catches `email.*`/`response.returned` |
| R-17 | **"response" entity ownership** ambiguous | L | M | EP-3/EP-5 | Fixed by ADR-008 (Ticket/Document/Mailbox/Flowable) | Clarify via a new ADR | Response text duplicated across services |
| R-18 | **Event idempotency/delivery** (duplicates, loss) | M | H | EP-3+ | Transactional Outbox, idempotent consumers, DLQ, correlation ID, unique external IDs | Manual reconciliation; replay from outbox | Duplicates create second tickets/tasks |
| R-19 | **Dictionary content** (classifier/product/closure_reason) not provided by business | M | M | EP-1 | Seed fixtures; clarify taxonomy with business (OPEN_QUESTIONS) | Temporary code set with later mapping | By EP-1 no approved classifier |
| R-20 | **Documentation policy overhead** (English-only, docstring coverage) slows a single developer | M | L | cross-cutting | Automated gates in CI (Ruff `D`, coverage tool), Google convention, templates; conversation stays in Russian (ADR-015) | Temporarily lower coverage target for specific documented exclusions | Coverage/English-Markdown checks block CI frequently |

## Risk monitoring

- High priority for early mitigation: **R-01, R-03, R-04** (addressed by EP-0F and
  provider/policy abstractions before their phases).
- Cross-cutting (continuous control): **R-07, R-08, R-10, R-11, R-12, R-18, R-20**.
- Post-MVP (do not block MVP): **R-06, R-13, R-14, R-15**.
