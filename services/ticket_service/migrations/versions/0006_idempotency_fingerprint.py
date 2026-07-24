"""Add the idempotency request fingerprint to the ticket.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23

Adds ``idempotency_fingerprint`` so a same-caller replay with a different payload is a conflict
rather than a silent replay. The idempotency key itself is now stored as a SHA-256 digest of the
subject-namespaced key, keeping it a per-caller namespace rather than a global lookup oracle
(CR-BFF-RR-BLOCKER-001). Only an additive nullable column is required.

Legacy rows registered before this change keep their raw, unscoped ``idempotency_key`` with a NULL
``idempotency_fingerprint``. Their original actor and canonical request cannot be reconstructed, so
they are not rewritten here; instead the create use case detects a retry of such a legacy key (raw
key present with a NULL fingerprint) and returns a non-disclosing 409 rather than creating a
duplicate regulatory record (CR-BFF-R3-HIGH-001).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ticket_service.infrastructure.migration_guards import abort_if_tables_not_empty

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_LEN = 64


def upgrade() -> None:
    """Apply the migration: add the nullable ``idempotency_fingerprint`` column."""
    op.add_column(
        "ticket", sa.Column("idempotency_fingerprint", sa.String(length=_CODE_LEN), nullable=True)
    )


def downgrade() -> None:
    """Revert the migration.

    Destructive for the added column. The guard aborts if ``ticket`` holds rows, so registered
    regulatory data is never dropped by a rollback (root ``CLAUDE.md``, docs/06).
    """
    abort_if_tables_not_empty("ticket")
    op.drop_column("ticket", "idempotency_fingerprint")
