"""Guards protecting identity and audit data during Alembic downgrades.

Downgrades that drop tables would physically destroy user accounts, role grants, and audit history.
Audit records must not be removed through an ordinary action (root ``CLAUDE.md``; docs/06 audit), so
these guards abort a destructive downgrade when a protected table still holds rows, forcing an
explicit forward-fix or a deliberate purge instead of silent data loss. Mirrors the ticket service's
guard (ADR-007 keeps such rules per-service rather than shared).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


class ProtectedDataPresentError(RuntimeError):
    """Raised when a destructive downgrade would delete non-empty protected data."""


def abort_if_tables_not_empty(*tables: str) -> None:
    """Abort the current downgrade if any named table contains rows.

    Args:
        *tables: Names of protected tables to check.

    Raises:
        ProtectedDataPresentError: If any table holds at least one row.
    """
    bind = op.get_bind()
    for table in tables:
        # Table names are internal constants (not user input), so the f-string is safe here.
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise ProtectedDataPresentError(
                f"refusing to run a destructive downgrade: protected table {table!r} still has "
                f"{count} row(s). Identity/audit data must not be deleted by a migration "
                f"(root CLAUDE.md, docs/06). Use a forward-fix migration or an explicit, audited "
                f"purge instead."
            )
