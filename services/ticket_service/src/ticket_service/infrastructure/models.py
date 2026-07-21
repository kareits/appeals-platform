"""SQLAlchemy models owned by the ticket service.

These tables realize the ticket data dictionary (docs/02): the regulatory ticket card, the parties
attached to it (consumer and representative), the business-configurable reference dictionaries, and
the per-year counter that backs registration-number allocation. The ticket carries an optimistic
locking ``version`` column (docs/02, TICKET_SERVICE invariants). No column stores binary content,
files, or full emails — those belong to the Document and Mailbox services (root ``CLAUDE.md`` data
ownership).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ticket_service.domain.enums import ApplicantType, DataSource, IdentifierType
from ticket_service.infrastructure.ids import uuid7

# Length caps for short coded values and free-text-ish identifiers. Codes reference dictionary
# entries; the values are kept generous to avoid churn while the taxonomy is still draft (Q-A1).
_CODE_LEN = 64
_SHORT_TEXT_LEN = 512


class Base(DeclarativeBase):
    """Declarative base for ticket-service ORM models."""


class Ticket(Base):
    """The regulatory appeal card and registry entry.

    The ``id`` is an internal UUIDv7 surrogate key; ``registration_number`` is the separate,
    human-facing business identifier (docs/02, ADR-003). Status and stage are projections driven by
    Flowable in later phases; at registration they default to the initial values. Decision, closure,
    and retention fields are nullable until the relevant lifecycle step records them.

    Attributes:
        id: Internal UUIDv7 primary key.
        registration_number: Unique business registration number.
        received_at: When the appeal was received (email arrival or manual entry).
        registered_at: When the appeal was registered in the system.
        source_channel_code: Intake channel code (dictionary ``channel``).
        subject: Short subject line of the appeal.
        description: Full appeal text.
        product_code: Credit-product code (dictionary ``product``).
        classifier_code: Question-classifier code (dictionary ``classifier``).
        priority_code: Priority code (dictionary ``priority``).
        current_status_code: Current status code (dictionary ``status``), Flowable projection.
        current_stage_code: Current stage code (dictionary ``stage``), Flowable projection.
        current_team_id: Responsible team, assigned by Flowable (nullable).
        current_assignee_id: Responsible employee, assigned by Flowable (nullable).
        legal_due_at: Regulatory deadline (nullable, ADR-009).
        internal_due_at: Internal SLA deadline (nullable, ADR-009).
        decision_code: Decision code (dictionary ``decision``), set before closure.
        decision_summary: Short decision summary, set before closure.
        decision_text: Full decision text, set before closure.
        decision_at: When the decision was made.
        decision_by: Employee who recorded the decision.
        closure_reason_code: Closure-reason code (dictionary ``closure_reason``), set at closure.
        closed_at: When the ticket was closed (nullable; not set automatically by a sent response).
        retention_until: Earliest purge-eligible date, set at closure (docs/01 retention).
        legal_hold: Whether the ticket is under legal hold and exempt from purge.
        version: Optimistic-locking version, managed by SQLAlchemy.
    """

    __tablename__ = "ticket"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    registration_number: Mapped[str] = mapped_column(String(_CODE_LEN), unique=True, index=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    source_channel_code: Mapped[str] = mapped_column(String(_CODE_LEN))
    subject: Mapped[str] = mapped_column(String(_SHORT_TEXT_LEN))
    description: Mapped[str] = mapped_column(Text())

    product_code: Mapped[str] = mapped_column(String(_CODE_LEN))
    classifier_code: Mapped[str] = mapped_column(String(_CODE_LEN))
    priority_code: Mapped[str] = mapped_column(String(_CODE_LEN))

    current_status_code: Mapped[str] = mapped_column(String(_CODE_LEN))
    current_stage_code: Mapped[str] = mapped_column(String(_CODE_LEN))
    current_team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    current_assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)

    legal_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    internal_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decision_code: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)
    decision_summary: Mapped[str | None] = mapped_column(String(_SHORT_TEXT_LEN), nullable=True)
    decision_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)

    closure_reason_code: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    retention_until: Mapped[date | None] = mapped_column(Date(), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean(), default=False)

    version: Mapped[int] = mapped_column(Integer(), nullable=False)

    # Optimistic locking: SQLAlchemy initializes ``version`` to 1 on insert and increments it on
    # each update, raising StaleDataError on a concurrent modification (docs/02 invariant).
    __mapper_args__ = {"version_id_col": version}

    applicants: Mapped[list[TicketApplicant]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )


class TicketApplicant(Base):
    """A party attached to a ticket: the consumer or a representative.

    Both roles share this table, distinguished by ``applicant_type`` (docs/02 Applicant entity).
    All demographic fields are nullable and must never block registration (docs/01). The national
    identifier is sensitive and is masked in UI, exports, and logs by default (Q-D3); it is stored
    here so authorized roles can access the full value.

    Attributes:
        id: Internal UUIDv7 primary key.
        ticket_id: Owning ticket.
        applicant_type: Whether this party is the consumer or a representative.
        full_name: Party full name (nullable).
        identifier_type: Kind of national identifier, IIN or BIN (nullable).
        identifier_value: The national identifier value; sensitive/maskable (nullable).
        email: Contact email (nullable).
        phone: Contact phone (nullable).
        gender_code: Gender code (dictionary ``gender``, nullable).
        birth_date: Date of birth (nullable).
        age: Age in years (nullable).
        region_code: Region code (dictionary ``region``, nullable).
        data_source: Provenance of the demographic data.
        representative_basis: Legal basis on which a representative acts (nullable).
    """

    __tablename__ = "ticket_applicant"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ticket.id", ondelete="CASCADE"), index=True
    )

    applicant_type: Mapped[ApplicantType] = mapped_column(
        Enum(ApplicantType, native_enum=False, length=_CODE_LEN)
    )
    full_name: Mapped[str | None] = mapped_column(String(_SHORT_TEXT_LEN), nullable=True)
    identifier_type: Mapped[IdentifierType | None] = mapped_column(
        Enum(IdentifierType, native_enum=False, length=_CODE_LEN), nullable=True
    )
    identifier_value: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)
    email: Mapped[str | None] = mapped_column(String(_SHORT_TEXT_LEN), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)
    gender_code: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)
    data_source: Mapped[DataSource] = mapped_column(
        Enum(DataSource, native_enum=False, length=_CODE_LEN)
    )
    representative_basis: Mapped[str | None] = mapped_column(String(_SHORT_TEXT_LEN), nullable=True)

    ticket: Mapped[Ticket] = relationship(back_populates="applicants")


class DictionaryEntry(Base):
    """A single reference-dictionary value (channel, product, classifier, status, and so on).

    Business-configurable taxonomies are stored as rows rather than code enums because their
    members are owned by the business and evolve independently (Q-A1). Display names carry business
    content and may be in Russian or Kazakh (ADR-015). Tickets store the ``code`` string, not a
    foreign key, matching the ``*_code`` typing in docs/02.

    Attributes:
        id: Surrogate primary key.
        dictionary_type: The dictionary this entry belongs to (for example, ``product``).
        code: The stable, code-side identifier, unique within its dictionary.
        display_name_ru: Russian display label (business content).
        display_name_kk: Kazakh display label (business content, nullable).
        sort_order: Ordering hint for presentation.
        is_active: Whether the entry is currently selectable.
    """

    __tablename__ = "dictionary_entry"
    __table_args__ = (
        UniqueConstraint("dictionary_type", "code", name="uq_dictionary_entry_type_code"),
    )

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    dictionary_type: Mapped[str] = mapped_column(String(_CODE_LEN), index=True)
    code: Mapped[str] = mapped_column(String(_CODE_LEN))
    display_name_ru: Mapped[str] = mapped_column(String(_SHORT_TEXT_LEN))
    display_name_kk: Mapped[str | None] = mapped_column(String(_SHORT_TEXT_LEN), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer(), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)


class RegistrationSequence(Base):
    """Per-year monotonic counter backing registration-number allocation.

    One row per calendar year holds the last issued sequence value. Allocation increments
    ``last_value`` under a row lock so concurrent registrations never receive the same number
    (uniqueness validation, TASK_01A). This is registry bookkeeping, not regulatory appeal data.

    Attributes:
        year: The calendar year (primary key).
        last_value: The last sequence number issued for that year.
    """

    __tablename__ = "registration_sequence"

    year: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer(), default=0)
