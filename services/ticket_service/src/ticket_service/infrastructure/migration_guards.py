"""Guards protecting regulatory and audit data during Alembic downgrades.

Downgrades that drop tables or columns would physically destroy regulatory appeals, comments,
unpublished events, and audit history — which the source requirements forbid removing through an
ordinary action (root ``CLAUDE.md``; docs/01 retention; docs/06 audit). These guards abort a
destructive downgrade when any protected table still holds rows, forcing an explicit forward-fix or
a deliberate purge instead of silent data loss. Reference data (dictionaries, the registration
counter) is not protected, so seed rollbacks remain allowed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


class RegulatoryDataPresentError(RuntimeError):
    """Raised when a destructive downgrade would delete non-empty protected data."""


def abort_if_tables_not_empty(*tables: str) -> None:
    """Abort the current downgrade if any named table contains rows.

    Args:
        *tables: Names of protected tables to check.

    Raises:
        RegulatoryDataPresentError: If any table holds at least one row.
    """
    bind = op.get_bind()
    for table in tables:
        # Table names are internal constants (not user input), so the f-string is safe here.
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RegulatoryDataPresentError(
                f"refusing to run a destructive downgrade: protected table {table!r} still has "
                f"{count} row(s). Regulatory/audit data must not be deleted by a migration "
                f"(root CLAUDE.md, docs/01, docs/06). Use a forward-fix migration or an explicit, "
                f"audited purge instead."
            )
