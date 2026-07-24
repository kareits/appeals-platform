"""Establish the BFF service's own database baseline (no tables).

Revision ID: 0001
Revises:
Create Date: 2026-07-23

This baseline reserves the gateway's own database/schema per the data-ownership boundary (ADR-004)
without creating any domain tables: the BFF is a stateless aggregator in EP-1 (TASK_01E-1) and
stores no domain data. Applying the migration creates only Alembic's ``alembic_version`` bookkeeping
table, so ``upgrade``/``downgrade`` are intentionally no-ops. Future persistent state (for example,
rate-limit counters) is added as a new revision rather than by editing this baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the baseline migration (no schema objects are created)."""


def downgrade() -> None:
    """Revert the baseline migration (nothing to drop)."""
