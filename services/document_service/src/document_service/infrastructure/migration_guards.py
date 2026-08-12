"""Guards protecting stored evidence during Alembic downgrades.

Document metadata is the only index of the bytes on the storage volume: dropping the table by a
rollback would orphan every stored file and destroy the ``document_id`` references other services
hold, which the source requirements forbid doing through an ordinary action (root ``CLAUDE.md``;
docs/01 retention; docs/06). The guard aborts a destructive downgrade while any protected table
still holds rows, forcing a forward-fix or a deliberate, audited purge instead of silent data loss.

Migrations never delete files: a downgrade removes schema only, and the storage volume is left
untouched so a re-upgrade can be reconciled against it (TASK_03A-1 rollback plan).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


class StoredDataPresentError(RuntimeError):
    """Raised when a destructive downgrade would orphan or delete stored document data."""


def abort_if_tables_not_empty(*tables: str) -> None:
    """Abort the current downgrade if any named table contains rows.

    Args:
        *tables: Names of protected tables to check.

    Raises:
        StoredDataPresentError: If any table holds at least one row.
    """
    bind = op.get_bind()
    for table in tables:
        # Table names are internal constants (not user input), so the f-string is safe here.
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise StoredDataPresentError(
                f"refusing to run a destructive downgrade: protected table {table!r} still has "
                f"{count} row(s). Dropping it would orphan the stored files and break the document "
                f"identifiers other services hold (root CLAUDE.md, docs/01, docs/06). Use a "
                f"forward-fix migration or an explicit, audited purge instead."
            )
