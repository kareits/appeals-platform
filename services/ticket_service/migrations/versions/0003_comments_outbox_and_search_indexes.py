"""Add comments, the transactional outbox, contract/idempotency fields, and search indexes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_LEN = 64
_SHORT_TEXT_LEN = 512

# Ticket columns indexed to back the TASK_01B search filters.
_TICKET_SEARCH_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_ticket_current_status_code", "current_status_code"),
    ("ix_ticket_current_stage_code", "current_stage_code"),
    ("ix_ticket_product_code", "product_code"),
    ("ix_ticket_classifier_code", "classifier_code"),
    ("ix_ticket_source_channel_code", "source_channel_code"),
    ("ix_ticket_current_assignee_id", "current_assignee_id"),
    ("ix_ticket_current_team_id", "current_team_id"),
    ("ix_ticket_received_at", "received_at"),
    ("ix_ticket_registered_at", "registered_at"),
    ("ix_ticket_contract_number", "contract_number"),
)


def upgrade() -> None:
    """Apply the migration: new ticket fields/indexes, comments, and the outbox."""
    op.add_column(
        "ticket", sa.Column("contract_number", sa.String(length=_CODE_LEN), nullable=True)
    )
    op.add_column(
        "ticket", sa.Column("idempotency_key", sa.String(length=_CODE_LEN), nullable=True)
    )
    op.create_index("ix_ticket_idempotency_key", "ticket", ["idempotency_key"], unique=True)
    for index_name, column in _TICKET_SEARCH_INDEXES:
        op.create_index(index_name, "ticket", [column])

    # Applicant search indexes (national identifier exact match; full-name partial match).
    op.create_index(
        "ix_ticket_applicant_identifier_value", "ticket_applicant", ["identifier_value"]
    )
    op.create_index("ix_ticket_applicant_full_name", "ticket_applicant", ["full_name"])

    op.create_table(
        "ticket_comment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ticket_comment_ticket_id", "ticket_comment", ["ticket_id"])

    op.create_table(
        "outbox_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=_SHORT_TEXT_LEN), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("producer", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("correlation_id", sa.String(length=_CODE_LEN), nullable=False),
        sa.Column("causation_id", sa.String(length=_CODE_LEN), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_outbox_event_event_id"),
    )
    op.create_index("ix_outbox_event_published_at", "outbox_event", ["published_at"])


def downgrade() -> None:
    """Revert the migration.

    Drops only structures introduced here; no regulatory appeal data is removed beyond the
    (empty-at-this-revision) comment/outbox tables (root ``CLAUDE.md``).
    """
    op.drop_index("ix_outbox_event_published_at", table_name="outbox_event")
    op.drop_table("outbox_event")
    op.drop_index("ix_ticket_comment_ticket_id", table_name="ticket_comment")
    op.drop_table("ticket_comment")
    op.drop_index("ix_ticket_applicant_full_name", table_name="ticket_applicant")
    op.drop_index("ix_ticket_applicant_identifier_value", table_name="ticket_applicant")
    for index_name, _ in _TICKET_SEARCH_INDEXES:
        op.drop_index(index_name, table_name="ticket")
    op.drop_index("ix_ticket_idempotency_key", table_name="ticket")
    op.drop_column("ticket", "idempotency_key")
    op.drop_column("ticket", "contract_number")
