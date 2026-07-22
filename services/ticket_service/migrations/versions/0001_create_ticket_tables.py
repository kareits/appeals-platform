"""Create ticket, applicant, dictionary, and registration-sequence tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ticket_service.domain.enums import ApplicantType, DataSource, IdentifierType
from ticket_service.infrastructure.migration_guards import abort_if_tables_not_empty

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_LEN = 64
_SHORT_TEXT_LEN = 512


def upgrade() -> None:
    """Apply the migration: create the ticket registry schema."""
    op.create_table(
        "ticket",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("registration_number", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_channel_code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("subject", sa.String(length=_SHORT_TEXT_LEN), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("product_code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("classifier_code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("priority_code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("current_status_code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("current_stage_code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("current_team_id", sa.Uuid(), nullable=True),
        sa.Column("current_assignee_id", sa.Uuid(), nullable=True),
        sa.Column("legal_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("internal_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_code", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("decision_summary", sa.String(length=_SHORT_TEXT_LEN), nullable=True),
        sa.Column("decision_text", sa.Text(), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_by", sa.Uuid(), nullable=True),
        sa.Column("closure_reason_code", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_ticket_registration_number",
        "ticket",
        ["registration_number"],
        unique=True,
    )

    op.create_table(
        "ticket_applicant",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column(
            "applicant_type",
            sa.Enum(ApplicantType, native_enum=False, length=_CODE_LEN),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=_SHORT_TEXT_LEN), nullable=True),
        sa.Column(
            "identifier_type",
            sa.Enum(IdentifierType, native_enum=False, length=_CODE_LEN),
            nullable=True,
        ),
        sa.Column("identifier_value", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("email", sa.String(length=_SHORT_TEXT_LEN), nullable=True),
        sa.Column("phone", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("gender_code", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("region_code", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column(
            "data_source",
            sa.Enum(DataSource, native_enum=False, length=_CODE_LEN),
            nullable=False,
        ),
        sa.Column("representative_basis", sa.String(length=_SHORT_TEXT_LEN), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ticket_applicant_ticket_id", "ticket_applicant", ["ticket_id"])

    op.create_table(
        "dictionary_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dictionary_type", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("code", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("display_name_ru", sa.String(length=_SHORT_TEXT_LEN), nullable=False),
        sa.Column("display_name_kk", sa.String(length=_SHORT_TEXT_LEN), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.UniqueConstraint("dictionary_type", "code", name="uq_dictionary_entry_type_code"),
    )
    op.create_index("ix_dictionary_entry_dictionary_type", "dictionary_entry", ["dictionary_type"])

    op.create_table(
        "registration_sequence",
        sa.Column("year", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("last_value", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Revert the migration: drop the ticket registry schema.

    Destructive: this drops the regulatory ``ticket`` and ``ticket_applicant`` tables. The guard
    aborts the downgrade if either still holds rows, so regulatory data is never deleted by a
    rollback (root ``CLAUDE.md``, docs/01). Use a forward-fix migration or an audited purge instead.
    """
    abort_if_tables_not_empty("ticket", "ticket_applicant")
    op.drop_table("registration_sequence")
    op.drop_index("ix_dictionary_entry_dictionary_type", table_name="dictionary_entry")
    op.drop_table("dictionary_entry")
    op.drop_index("ix_ticket_applicant_ticket_id", table_name="ticket_applicant")
    op.drop_table("ticket_applicant")
    op.drop_index("ix_ticket_registration_number", table_name="ticket")
    op.drop_table("ticket")
