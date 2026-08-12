"""Create the document metadata table.

Revision ID: 0001
Revises:
Create Date: 2026-08-11

Establishes the document service's own schema (ADR-004): a single ``document`` table that indexes
every object on the storage volume. ``ticket_id`` and ``message_id`` are plain UUID columns with no
foreign key, because the appeals and mail messages they identify live in other services' databases
and a cross-service database dependency is forbidden (root ``CLAUDE.md``).

The hash (``sha256``) and antivirus (``scan_status``) fields of the data dictionary are added by
TASK_03A-2 as a separate revision, so this migration is the file-boundary baseline only.

**Rollback plan.** The downgrade drops the table and the enum type but never touches the storage
volume: stored files survive a rollback, and the guard below refuses to drop a non-empty table so
the only index of those files cannot be destroyed by an ordinary rollback.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from document_service.infrastructure.migration_guards import abort_if_tables_not_empty

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_LEN = 64
_FILENAME_LEN = 255
_STORAGE_KEY_LEN = 128
_CONTENT_TYPE_LEN = 255

# The storage lifecycle states as an immutable value list for the enum column. Kept as literals (not
# an import of the domain enum) so this migration is a self-contained snapshot: changing the
# lifecycle later is a new migration, never an edit to this one.
_STATUS_VALUES = (
    "UPLOADING",
    "UPLOADED",
    "PENDING_SCAN",
    "CLEAN",
    "AVAILABLE",
    "INFECTED",
    "UPLOAD_FAILED",
    "DELETED",
)


def upgrade() -> None:
    """Apply the migration: create the ``document`` table and its indexes."""
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=_FILENAME_LEN), nullable=False),
        sa.Column("storage_backend", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("storage_key", sa.String(length=_STORAGE_KEY_LEN), nullable=False),
        sa.Column("content_type", sa.String(length=_CONTENT_TYPE_LEN), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("document_type_code", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum(*_STATUS_VALUES, name="document_status"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migrated_at", sa.DateTime(timezone=True), nullable=True),
        # A storage key is generated randomly per upload; the constraint turns a collision or a
        # buggy re-use into an insert failure instead of a silent overwrite of stored bytes.
        sa.UniqueConstraint("storage_key", name="uq_document_storage_key"),
    )
    op.create_index("ix_document_ticket_id_created_at", "document", ["ticket_id", "created_at"])
    op.create_index("ix_document_message_id", "document", ["message_id"])
    op.create_index("ix_document_status", "document", ["status"])


def downgrade() -> None:
    """Revert the migration, refusing to drop non-empty document metadata.

    The metadata table is the only index of the files on the storage volume: dropping it would
    orphan every stored object and break the document identifiers other services hold, which must
    not happen through an ordinary action (root ``CLAUDE.md``; docs/01; docs/06). The guard aborts
    while rows exist. Stored files are never deleted by this migration in either direction.
    """
    abort_if_tables_not_empty("document")
    op.drop_index("ix_document_status", table_name="document")
    op.drop_index("ix_document_message_id", table_name="document")
    op.drop_index("ix_document_ticket_id_created_at", table_name="document")
    op.drop_table("document")
    # Drop the enum type on backends that materialize one (PostgreSQL); a no-op on SQLite.
    sa.Enum(*_STATUS_VALUES, name="document_status").drop(op.get_bind(), checkfirst=True)
