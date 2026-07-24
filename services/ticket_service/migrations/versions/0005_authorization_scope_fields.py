"""Add authorization data-scope fields to the ticket.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23

Adds ``registered_by`` (the verified subject who registered the appeal, for ownership-based data
scope) and ``is_confidential`` (restricts the appeal to an oversight/audit role subset). Both back
the Ticket Service's independent authorization enforcement (CR-BFF-BLOCKER-001, ADR-0008).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ticket_service.infrastructure.migration_guards import abort_if_tables_not_empty

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration: add ``registered_by`` and ``is_confidential`` to ``ticket``.

    Backfill is **fail-closed** for confidentiality (CR-BFF-RR-HIGH-002): the column is added with a
    ``FALSE`` server default (so future inserts default to non-confidential; the ORM always supplies
    the value explicitly), but every pre-existing row — whose regulated classification was never
    evaluated — is then set to ``TRUE`` so it is treated as confidential until an authorized process
    reclassifies it. Unknown classification must not be interpreted as public. ``registered_by`` is
    left NULL for existing rows (unknown registrant); an authorized backfill can set it later.
    """
    op.add_column("ticket", sa.Column("registered_by", sa.Uuid(), nullable=True))
    op.add_column(
        "ticket",
        sa.Column(
            "is_confidential",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_ticket_registered_by", "ticket", ["registered_by"])
    # Fail-closed: pre-existing appeals of unknown classification become confidential until review.
    op.execute(sa.text("UPDATE ticket SET is_confidential = TRUE"))


def downgrade() -> None:
    """Revert the migration.

    Destructive for the added columns. The guard aborts if ``ticket`` holds rows, so registered
    regulatory data is never dropped by a rollback (root ``CLAUDE.md``, docs/06).
    """
    abort_if_tables_not_empty("ticket")
    op.drop_index("ix_ticket_registered_by", table_name="ticket")
    op.drop_column("ticket", "is_confidential")
    op.drop_column("ticket", "registered_by")
