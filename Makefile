# Task runner for the MFO Appeals Platform monorepo.
# `UV` defaults to `python -m uv` so targets work even when the `uv` executable
# is not on PATH. Override with `make UV=uv <target>` if you prefer the binary.

UV ?= python -m uv
COMPOSE ?= docker compose -f infrastructure/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help install lint format type test docstrings docs-lang migrate check up down logs ps

help: ## Show available targets.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Sync the workspace virtual environment with all members and dev tools.
	$(UV) sync --all-packages --dev

lint: ## Run Ruff lint checks (includes docstring rules, ADR-015).
	$(UV) run ruff check .

format: ## Auto-format the codebase with Ruff.
	$(UV) run ruff format .

type: ## Run mypy static type checks.
	$(UV) run mypy

test: ## Run the test suite.
	$(UV) run pytest

docstrings: ## Verify docstring coverage (interrogate, target 100%).
	$(UV) run interrogate -c pyproject.toml .

docs-lang: ## Verify technical Markdown files are written in English (ADR-015).
	$(UV) run python tools/check_english_markdown.py

check: lint type test docstrings docs-lang ## Run all quality gates.

up: ## Build and start the local infrastructure in the background.
	$(COMPOSE) up --build -d

down: ## Stop the local infrastructure and remove containers.
	$(COMPOSE) down

logs: ## Follow logs from all infrastructure services.
	$(COMPOSE) logs -f

ps: ## Show the status of infrastructure services.
	$(COMPOSE) ps

migrate: ## Apply demo-service database migrations against the compose PostgreSQL.
	$(COMPOSE) run --rm -w /app/services/demo_service demo_service alembic upgrade head
