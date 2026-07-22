"""Add closure/SLA ticket fields and the audit log.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ticket_service.infrastructure.migration_guards import abort_if_tables_not_empty

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_LEN = 64
_SHORT_TEXT_LEN = 512


def upgrade() -> None:
    """Apply the migration: closure/SLA ticket fields and the audit_log table."""
    op.add_column(
        "ticket", sa.Column("sla_policy_version", sa.String(length=_CODE_LEN), nullable=True)
    )
    op.add_column(
        "ticket", sa.Column("response_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ticket", sa.Column("no_response_reason", sa.String(length=_SHORT_TEXT_LEN), nullable=True)
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    """Revert the migration.

    Destructive: drops ``audit_log`` and removes closure/SLA ticket columns. The guard aborts if
    ``audit_log`` or ``ticket`` hold rows, so audit history and closure evidence are never deleted
    by a rollback (root ``CLAUDE.md``, docs/06).
    """
    abort_if_tables_not_empty("ticket", "audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_column("ticket", "no_response_reason")
    op.drop_column("ticket", "response_sent_at")
    op.drop_column("ticket", "sla_policy_version")
