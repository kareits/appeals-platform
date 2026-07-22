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

## 7. Report and commit

Report the outcome against the Definition of Done (root `CLAUDE.md`, items 1–12) in Russian,
faithfully (including anything skipped or failing). **Commit only when the user asks**; if on the
default branch and the change is substantial, branch first. End commit messages with the
Co-Authored-By trailer.

## When to write a fuller prompt instead

The one-line prompt is enough for on-plan work. Provide a detailed prompt only when the phase
deviates from the plan, or when new inputs change scope (for example, a new policy) — those are
easier to convey as text than to encode in the plan.
