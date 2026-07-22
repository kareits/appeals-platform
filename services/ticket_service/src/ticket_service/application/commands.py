"""Command and query data-transfer objects for ticket use cases.

Plain dataclasses decouple the application layer from the HTTP/API layer (FastAPI/Pydantic) so use
cases can be unit-tested without a web framework.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from ticket_service.domain.enums import ApplicantType, DataSource, IdentifierType


@dataclass(frozen=True)
class ApplicantInput:
    """Input describing a party (consumer or representative) at registration.

    Attributes:
        applicant_type: Whether this party is the consumer or a representative.
        data_source: Provenance of the party's data.
        full_name: Full name, if known.
        identifier_type: Kind of national identifier, if known.
        identifier_value: The national identifier value, if known (stored, masked in outputs).
        email: Contact email, if known.
        phone: Contact phone, if known.
        gender_code: Gender code, if known.
        birth_date: Date of birth, if known.
        age: Age in years, if known.
        region_code: Region code, if known.
        representative_basis: Legal basis on which a representative acts, if applicable.
    """

    applicant_type: ApplicantType
    data_source: DataSource
    full_name: str | None = None
    identifier_type: IdentifierType | None = None
    identifier_value: str | None = None
    email: str | None = None
    phone: str | None = None
    gender_code: str | None = None
    birth_date: date | None = None
    age: int | None = None
    region_code: str | None = None
    representative_basis: str | None = None


@dataclass(frozen=True)
class CreateTicketCommand:
    """Input to register an appeal manually.

    Attributes:
        received_at: When the appeal was received.
        source_channel_code: Intake channel code.
        subject: Short subject line.
        description: Full appeal text.
        product_code: Credit-product code.
        classifier_code: Question-classifier code.
        priority_code: Priority code.
        applicant: The consumer party.
        contract_number: Related credit-contract number, if any.
        representative: An optional representative party.
        idempotency_key: Optional client key making the registration retry-safe.
    """

    received_at: datetime
    source_channel_code: str
    subject: str
    description: str
    product_code: str
    classifier_code: str
    priority_code: str
    applicant: ApplicantInput
    contract_number: str | None = None
    representative: ApplicantInput | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class UpdateTicketCommand:
    """Input to update editable appeal-card details.

    Only fields listed in :attr:`provided` are applied, so an explicit ``None`` (clear the value)
    is distinguished from "not supplied". Status, stage, and assignment are not updatable here.

    Attributes:
        ticket_id: The ticket to update.
        expected_version: Version the client last observed (optimistic locking).
        subject: New subject line, if provided.
        description: New appeal text, if provided.
        source_channel_code: New intake channel code, if provided.
        contract_number: New contract number, if provided (``None`` clears it).
        provided: Names of the fields that were supplied and should be applied.
    """

    ticket_id: uuid.UUID
    expected_version: int
    subject: str | None = None
    description: str | None = None
    source_channel_code: str | None = None
    contract_number: str | None = None
    provided: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ClassifyTicketCommand:
    """Input to set an appeal's classification.

    Attributes:
        ticket_id: The ticket to classify.
        expected_version: Version the client last observed (optimistic locking).
        product_code: Credit-product code.
        classifier_code: Question-classifier code.
        priority_code: Priority code.
    """

    ticket_id: uuid.UUID
    expected_version: int
    product_code: str
    classifier_code: str
    priority_code: str


@dataclass(frozen=True)
class AddCommentCommand:
    """Input to add a comment to an appeal.

    Attributes:
        ticket_id: The ticket to comment on.
        author_id: Identifier of the comment author.
        body: The comment text.
    """

    ticket_id: uuid.UUID
    author_id: uuid.UUID
    body: str


@dataclass(frozen=True)
class TicketSearchQuery:
    """Filters and pagination for appeal search.

    All filters are optional and combined with AND. Codes and identifiers match exactly; full name
    matches case-insensitively as a substring; date bounds are inclusive.

    Attributes:
        registration_number: Exact registration number.
        identifier_value: Exact national identifier of an attached party.
        full_name: Case-insensitive partial match on a party's full name.
        contract_number: Exact related contract number.
        status_code: Current status code.
        stage_code: Current stage code.
        product_code: Credit-product code.
        classifier_code: Question-classifier code.
        channel_code: Intake channel code.
        assignee_id: Current assignee identifier.
        team_id: Current team identifier.
        received_from: Inclusive lower bound on ``received_at``.
        received_to: Inclusive upper bound on ``received_at``.
        registered_from: Inclusive lower bound on ``registered_at``.
        registered_to: Inclusive upper bound on ``registered_at``.
        page: 1-based page number.
        page_size: Page size.
    """

    registration_number: str | None = None
    identifier_value: str | None = None
    full_name: str | None = None
    contract_number: str | None = None
    status_code: str | None = None
    stage_code: str | None = None
    product_code: str | None = None
    classifier_code: str | None = None
    channel_code: str | None = None
    assignee_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    received_from: datetime | None = None
    received_to: datetime | None = None
    registered_from: datetime | None = None
    registered_to: datetime | None = None
    page: int = 1
    page_size: int = 20
