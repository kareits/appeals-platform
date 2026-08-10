# SESSION_PROTOCOL — Standard workflow for a task session

The default procedure for implementing any subtask from
[DETAILED_TASK_INDEX.md](DETAILED_TASK_INDEX.md). It exists so a session can be started with a
one-line prompt (for example, "Implement TASK_00B per tasks/SESSION_PROTOCOL.md"); all scope,
Definition of Done, and boundaries already live in the planning documents.

Run one subtask per session (context hygiene, R-12). Communicate with the user in Russian; produce
English technical artifacts (ADR-015).

## 1. Load context

Read only what the phase needs:

- root [`CLAUDE.md`](../CLAUDE.md) — mandatory rules, language/naming/documentation policy;
- [`docs/CONTEXT_LOADING_GUIDE.md`](../docs/CONTEXT_LOADING_GUIDE.md) — the "must read" and "if
  needed" documents for this phase, plus which services may and may not be changed;
- the subtask entry in [`DETAILED_TASK_INDEX.md`](DETAILED_TASK_INDEX.md) — scope, data
  (migration/backfill/rollback/validation), DoD-specific items, and the independent check;
- the phase section of [`docs/IMPLEMENTATION_PLAN.md`](../docs/IMPLEMENTATION_PLAN.md) —
  Goal/API/Events/Data/Acceptance/Out-of-scope for the current EP, which refines the subtask;
- [`docs/DECISION_LOG.md`](../docs/DECISION_LOG.md) and
  [`docs/DOCUMENT_PRECEDENCE.md`](../docs/DOCUMENT_PRECEDENCE.md) for the governing decisions.

Do not read the whole document set — only the phase's required files.

## 2. Plan and confirm

Propose a short plan and file/directory layout in Russian, then wait for confirmation before
writing code. Use `AskUserQuestion` for genuine forks (tools, boundaries). This step may run in
Plan Mode.

## 3. Implement

Work in small, verifiable steps within the allowed set of services (per CONTEXT_LOADING_GUIDE).
Contracts first (OpenAPI/JSON Schema + contract tests), then implementation. Keep to the
architectural prohibitions in `chatgpt_docs/CLAUDE.md` and the root `CLAUDE.md`.

## 4. Data changes

For any subtask that changes data, deliver and verify: **migration**, **backfill**, **rollback**,
and **validation** (as recorded for the subtask in the index).

## 5. Run the quality gates

All must pass:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run interrogate -c pyproject.toml .
uv run python tools/check_english_markdown.py
```

(or `make check`). Fix issues until green.

## 6. Update documentation

Where behavior or boundaries changed: service `README.md` and `SERVICE_MAP.md`, OpenAPI/event
descriptions, architecture docs, and a new ADR under `docs/adr/` for significant decisions. Every
new/modified module, class, function, and method has an English Google-style docstring.

## 7. Prepare the code-review prompt

Before requesting review (and before any commit), prepare an independent code-review context package
using the shared template in [`reviews/UNIVERSAL_CODE_REVIEW_AGENT_PROMPT.md`](../reviews/UNIVERSAL_CODE_REVIEW_AGENT_PROMPT.md).
This step is mandatory for every implementation task. Fill in **every** field of that template's
context block from the repository — never substitute an unknown value with an invented fact:

- Task ID and title; the statement path(s) (`tasks/DETAILED_TASK_INDEX.md`, the current EP section of
  `docs/IMPLEMENTATION_PLAN.md`, `docs/CONTEXT_LOADING_GUIDE.md`).
- The developer report. When no report file exists, write it to `reviews/DEV_REPORT_<TASK_ID>.md`
  (acceptance-criteria mapping, changes by component, design decisions to scrutinize, exact gate
  results, what was not run, uncommitted state, and carried-over cross-task open findings).
- The previous relevant review section in `reviews/CODE_REVIEW_REPORT.md` (or `NONE` for a first
  pass), including any carried-over open cross-task findings that must not be treated as closed.
- Branch, base/expected HEAD, and whether the change is committed.
- The reviewer's allowed change scope (`NONE`, or only `reviews/CODE_REVIEW_REPORT.md` — append a new
  numbered section, do not rewrite earlier ones).
- Environment constraints (uv invoked as `python -m uv …` or via the repo `.venv`; Compose E2E only
  when infrastructure/migrations/env changed; pre-existing unrelated working-tree changes the
  reviewer must not touch).

These review artifacts are English technical documents (ADR-015). `reviews/` is git-ignored, so the
report and any prompt files stay local. Deliver the filled context block to the user so it can be
handed to a review agent in a fresh session.

## 8. Report and commit

Report the outcome against the Definition of Done (root `CLAUDE.md`, items 1–12) in Russian,
faithfully (including anything skipped or failing). **Commit only when the user asks**; if on the
default branch and the change is substantial, branch first. End commit messages with the
Co-Authored-By trailer.

## When to write a fuller prompt instead

The one-line prompt is enough for on-plan work. Provide a detailed prompt only when the phase
deviates from the plan, or when new inputs change scope (for example, a new policy) — those are
easier to convey as text than to encode in the plan.
