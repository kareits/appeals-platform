"""Create IAM team, user, user-role, and audit-log tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from iam_service.infrastructure.migration_guards import abort_if_tables_not_empty

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_LEN = 64
_NAME_LEN = 255

# The seven platform roles as an immutable value list for the enum column. Kept as literals (not an
# import of the domain enum) so this migration is a self-contained snapshot: adding a role later is
# a new migration, never an edit to this one.
_ROLE_VALUES = (
    "EMPLOYEE",
    "SUPERVISOR",
    "FIRST_LINE_READONLY",
    "OMBUDSMAN",
    "ANALYST",
    "ADMIN",
    "AUDITOR",
)


def upgrade() -> None:
    """Apply the migration: create the IAM identity and audit schema."""
    op.create_table(
        "iam_team",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("name", sa.String(length=_NAME_LEN), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("code", name="uq_iam_team_code"),
    )
    op.create_table(
        "iam_user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(length=_NAME_LEN), nullable=False),
        sa.Column("full_name", sa.String(length=_NAME_LEN), nullable=False),
        sa.Column("email", sa.String(length=_NAME_LEN), nullable=True),
        sa.Column("password_hash", sa.String(length=_NAME_LEN), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("iam_team.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("username", name="uq_iam_user_username"),
    )
    op.create_table(
        "iam_user_role",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("iam_user.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.Enum(*_ROLE_VALUES, name="iam_role"), nullable=False),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "role", name="uq_iam_user_role"),
    )
    op.create_table(
        "iam_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=_NAME_LEN), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    """Revert the migration, refusing to drop non-empty identity or audit data.

    Identity accounts, role grants, and audit history must not be destroyed by an ordinary
    downgrade (root ``CLAUDE.md``; docs/06). The guard aborts when any protected table still holds
    rows; run an explicit, audited purge first if removal is genuinely intended.
    """
    abort_if_tables_not_empty("iam_audit_log", "iam_user_role", "iam_user")
    op.drop_table("iam_audit_log")
    op.drop_table("iam_user_role")
    op.drop_table("iam_user")
    op.drop_table("iam_team")
    # Drop the enum type on backends that materialize one (PostgreSQL); a no-op on SQLite.
    sa.Enum(*_ROLE_VALUES, name="iam_role").drop(op.get_bind(), checkfirst=True)
