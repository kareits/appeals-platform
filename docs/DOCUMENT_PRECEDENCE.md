# DOCUMENT_PRECEDENCE — Document Precedence

Defines which document is the source of truth when project materials conflict.

## Document classes

1. **Source requirements (read-only):** the `chatgpt_docs/` directory — the original requirements
   set (README, CLAUDE.md, `docs/00–08`, `services/*`, `tasks/TASK_00–06`, `contracts/`,
   `orchestration/`).
   - Treated as **read-only**: during planning and implementation, files under `chatgpt_docs/`
     are **not modified or deleted**.
   - Serves as the primary source of business and regulatory requirements.
   - May remain in Russian (ADR-015).

2. **Approved decisions:** root `CLAUDE.md`, [`docs/DECISION_LOG.md`](DECISION_LOG.md), and future
   ADR documents.
   - Record approved architectural and process decisions, including deviations from the source set.

3. **Planning documents:** the other files in `docs/` (ROADMAP, IMPLEMENTATION_PLAN,
   DEPENDENCY_MAP, RISK_REGISTER, OPEN_QUESTIONS, CONTEXT_LOADING_GUIDE) and
   `tasks/DETAILED_TASK_INDEX.md`.
   - Operationalize requirements and decisions into a work plan.

4. **Contracts & orchestration (at implementation):** OpenAPI/JSON Schema in `contracts/` and
   BPMN/DMN in `orchestration/`.
   - Technical source of truth for APIs/events and processes once created.

## Precedence order on conflict

From highest to lowest:

```
1. Root CLAUDE.md / ADR / DECISION_LOG (approved decisions)
2. Contracts & orchestration (once created, within the bounds allowed by decisions)
3. Planning documents (docs/*, tasks/DETAILED_TASK_INDEX.md)
4. Source requirements (chatgpt_docs/*)
```

**Rule:** if an approved decision (root CLAUDE.md / ADR / DECISION_LOG) conflicts with
`chatgpt_docs/`, the **decision wins**. The source text in `chatgpt_docs/` is not edited; the
divergence is recorded as a DECISION_LOG entry referencing the original item.

## Conflict-resolution procedure

1. Conflict found → record it in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) if an external answer is
   required; otherwise record it directly in DECISION_LOG.
2. Make a decision → add an `ADR-NNN` entry to DECISION_LOG with: decision, rationale, reference
   to the source item `chatgpt_docs/...`, consequences.
3. If needed, update planning documents and (at implementation) contracts/orchestration.
4. `chatgpt_docs/` stays unchanged.

## Already-recorded deviations from the source requirements

| Deviation | Decided in | Source item |
|---|---|---|
| Reorder TASK_03A→TASK_02→TASK_03B | ADR-005 | `chatgpt_docs/README.md` (order), `tasks/TASK_02`, `tasks/TASK_03` |
| Canonical events `mail/ticket/response`, ban `email.*`/`response.returned` | ADR-006 | `docs/03`, `docs/05`, `docs/04`, `services/NOTIFICATION_SERVICE.md` |
| Shared-library boundaries (observability/http/testing) | ADR-007 | `docs/03`, `services/*` |
| ResponseDraft ownership | ADR-008 | `services/BFF_SERVICE.md`, `docs/02`, `docs/07` |
| SLA/business-calendar ownership | ADR-009 | `docs/01`, `docs/04` |
| Reporting via read-model in Ticket Service | ADR-011 | `tasks/TASK_05`, `services/TICKET_SERVICE.md` |
| Bootstrap without scaffolding all services | ADR-013 | `tasks/TASK_00` |
| English-only technical code and documentation | ADR-015 | `chatgpt_docs/*` (Russian source retained) |
