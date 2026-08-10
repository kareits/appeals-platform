# Solva Appeals Platform

Monorepo for the Solva Appeals Platform — an internal MFO platform for registering, processing,
controlling, analyzing, and storing written appeals from consumers of financial services.

> Planning and requirements live in [`docs/`](docs/), [`tasks/`](tasks/), and the read-only source
> set [`chatgpt_docs/`](chatgpt_docs/). Mandatory engineering rules are in the root
> [`CLAUDE.md`](CLAUDE.md). Language and documentation policy: English for technical artifacts,
> Russian for user conversation and business content (ADR-015).

## Repository layout

```
apps/            Frontend applications (added later)
services/        Backend services; demo_service is the reference template
libs/            Shared platform libraries (observability / http / testing only, ADR-007)
orchestration/   BPMN/DMN process models (added in EP-3)
contracts/       OpenAPI and JSON Schema contracts (added from TASK_00C)
infrastructure/  Docker Compose and deployment assets (added in TASK_00B)
tools/           Repository tooling scripts
docs/            Planning documents and ADRs
tasks/           Detailed task index
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python project and workspace manager).
- Python 3.12+ (uv can provision it: `uv python install 3.12`).

### Finding uv when the `uv` binary is not on PATH

On some machines (notably Windows dev boxes) the standalone `uv` executable is not on `PATH`, so a
bare `uv ...` fails with "command not found". uv is still usable — check these fallbacks in order:

1. **uv as a Python module** — uv is commonly installed into the interpreter, so
   `python -m uv --version` works even when the binary is absent. Prefix every command with
   `python -m`, e.g. `python -m uv run pytest`. This is the canonical invocation on such machines.
2. **The workspace environment directly** — after a sync, `.venv/` at the repo root holds the
   Python 3.12 toolchain. Run a tool without uv via `.venv/Scripts/<tool>` (Windows) or
   `.venv/bin/<tool>` (POSIX), e.g. `.venv/Scripts/ruff check .`, `.venv/Scripts/pytest`.

Do not assume "uv not on PATH" means uv is unavailable — verify with `python -m uv --version` and
inspect `.venv/` before falling back to any other approach.

## Getting started

```bash
uv sync --all-packages --dev      # create the workspace virtual environment
uv run pytest                     # run tests
uv run ruff check .               # lint (includes docstring rules)
uv run mypy                       # static type checks
uv run interrogate -c pyproject.toml .   # docstring coverage (100% target)
uv run python tools/check_english_markdown.py  # English-Markdown check
```

If the `uv` binary is not on `PATH`, prefix each command with `python -m` (for example,
`python -m uv run pytest`); see "Finding uv" above.

A `Makefile` wraps these commands (`make install`, `make check`, ...). It defaults to
`python -m uv` so it works even when the `uv` binary is not on PATH. When `make` itself is
unavailable (e.g. a bare Windows shell), run the `uv run ...` / `python -m uv run ...` commands
directly.

## Scope of this bootstrap (TASK_00A)

Delivered: monorepo skeleton, three shared libraries, one demonstration service with health
endpoints and a sample Alembic migration, and the documentation/quality tooling. Docker Compose
infrastructure (TASK_00B) and CI plus the event-envelope schema (TASK_00C) are added next. See
[tasks/DETAILED_TASK_INDEX.md](tasks/DETAILED_TASK_INDEX.md).
