"""Pydantic request/response schemas for the ticket API.

All models serialize with camelCase field names (docs/05). Response mappers apply identifier
masking so full national identifiers never leave the service in API payloads (docs/06, Q-D3).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel

from ticket_service.domain.enums import ApplicantType, DataSource, IdentifierType
from ticket_service.infrastructure.masking import mask_identifier
from ticket_service.infrastructure.models import Ticket, TicketApplicant, TicketComment

# Bounded input types aligned with the database column limits, so oversized/blank input is rejected
# with 422 by Pydantic instead of failing only in PostgreSQL (CR-MEDIUM-002). ``CodeStr`` matches a
# 64-char coded column; ``SubjectStr`` a 512-char subject; ``BodyStr`` a non-blank free-text field.
# Constraints are mirrored in contracts/openapi/ticket-service.v1.yaml (CR-MEDIUM-006 parity).
CodeStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
SubjectStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
BodyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# Optimistic-locking version: positive, matching the contract's ``minimum: 1``.
VersionInt = Annotated[int, Field(ge=1)]


class RequestModel(BaseModel):
    """Strict base for HTTP request bodies.

    Input must use the camelCase aliases (``populate_by_name=False``) and unknown properties are
    rejected (``extra="forbid"``), so the runtime schema advertises ``additionalProperties: false``
    and matches the committed contract exactly (CR-MEDIUM-006 parity).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid")


class ResponseModel(BaseModel):
    """Base for HTTP responses: camelCase output, snake_case construction by the mappers."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApplicantModel(RequestModel):
    """Request model for a party attached to an appeal.

    Attributes:
        applicant_type: Whether this party is the consumer or a representative.
        data_source: Provenance of the party's data.
        full_name: Full name, if known.
        identifier_type: Kind of national identifier, if known.
        identifier_value: National identifier value, if known (masked in responses).
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
    full_name: SubjectStr | None = None
    identifier_type: IdentifierType | None = None
    identifier_value: CodeStr | None = None
    email: SubjectStr | None = None
    phone: CodeStr | None = None
    gender_code: CodeStr | None = None
    birth_date: date | None = None
    age: int | None = None
    region_code: CodeStr | None = None
    representative_basis: SubjectStr | None = None


class CreateTicketRequest(RequestModel):
    """Request body to register an appeal.

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
        is_confidential: Whether to restrict the appeal to the confidential-access role subset.
    """

    received_at: AwareDatetime
    source_channel_code: CodeStr
    subject: SubjectStr
    description: BodyStr
    product_code: CodeStr
    classifier_code: CodeStr
    priority_code: CodeStr
    applicant: ApplicantModel
    contract_number: CodeStr | None = None
    representative: ApplicantModel | None = None
    is_confidential: bool = False

    @model_validator(mode="after")
    def _check_party_roles(self) -> Self:
        """Ensure the primary party is the consumer and the representative is a representative.

        Returns:
            The validated request.

        Raises:
            ValueError: If a party carries the wrong ``applicantType``.
        """
        if self.applicant.applicant_type is not ApplicantType.CONSUMER:
            raise ValueError("applicant must have applicantType CONSUMER")
        if (
            self.representative is not None
            and self.representative.applicant_type is not ApplicantType.REPRESENTATIVE
        ):
            raise ValueError("representative must have applicantType REPRESENTATIVE")
        return self


class UpdateTicketRequest(RequestModel):
    """Request body to update editable appeal-card details.

    Only supplied fields are applied; ``expected_version`` enforces optimistic locking.

    Attributes:
        expected_version: Version the client last observed.
        subject: New subject line, if supplied.
        description: New appeal text, if supplied.
        source_channel_code: New intake channel code, if supplied.
        contract_number: New contract number, if supplied (``None`` clears it).
    """

    expected_version: VersionInt
    subject: SubjectStr | None = None
    description: BodyStr | None = None
    source_channel_code: CodeStr | None = None
    contract_number: CodeStr | None = None


class ClassifyRequest(RequestModel):
    """Request body to classify an appeal.

    Attributes:
        expected_version: Version the client last observed.
        product_code: Credit-product code.
        classifier_code: Question-classifier code.
        priority_code: Priority code.
    """

    expected_version: VersionInt
    product_code: CodeStr
    classifier_code: CodeStr
    priority_code: CodeStr


class RecordDecisionRequest(RequestModel):
    """Request body to record a decision.

    The deciding employee is derived server-side from the authenticated caller and is not part of
    the request (CR-BFF-BLOCKER-001 trusted actor).

    Attributes:
        expected_version: Version the client last observed.
        decision_code: Decision code (dictionary ``decision``).
        decision_text: Full decision text.
        decision_summary: Optional short decision summary.
    """

    expected_version: VersionInt
    decision_code: CodeStr
    decision_text: BodyStr
    decision_summary: SubjectStr | None = None


class CloseTicketRequest(RequestModel):
    """Request body to close an appeal.

    Attributes:
        expected_version: Version the client last observed.
        closure_reason_code: Closure-reason code (dictionary ``closure_reason``).
        response_sent_at: When a response was sent, if any.
        no_response_reason: Justification when no response was sent.
    """

    expected_version: VersionInt
    closure_reason_code: CodeStr
    response_sent_at: AwareDatetime | None = None
    no_response_reason: SubjectStr | None = None


class LegalHoldRequest(RequestModel):
    """Request body to set or clear a legal hold.

    Attributes:
        expected_version: Version the client last observed.
        legal_hold: The desired legal-hold state.
        reason: Optional reason recorded in the audit log.
    """

    expected_version: VersionInt
    legal_hold: bool
    reason: str | None = None


class CommentRequest(RequestModel):
    """Request body to add a comment.

    The author is derived server-side from the authenticated caller and is not part of the request
    (CR-BFF-BLOCKER-001 trusted actor).

    Attributes:
        body: Comment text.
    """

    body: BodyStr


class ApplicantResponse(ResponseModel):
    """Response model for a party; the national identifier is masked.

    Attributes:
        id: Party identifier.
        applicant_type: Party role.
        full_name: Full name, if known.
        identifier_type: Kind of national identifier, if known.
        identifier_masked: Masked national identifier, if any.
        email: Contact email, if known.
        phone: Contact phone, if known.
        gender_code: Gender code, if known.
        birth_date: Date of birth, if known.
        age: Age in years, if known.
        region_code: Region code, if known.
        data_source: Provenance of the data.
        representative_basis: Legal basis for a representative, if applicable.
    """

    id: uuid.UUID
    applicant_type: ApplicantType
    full_name: str | None
    identifier_type: IdentifierType | None
    identifier_masked: str | None
    email: str | None
    phone: str | None
    gender_code: str | None
    birth_date: date | None
    age: int | None
    region_code: str | None
    data_source: DataSource
    representative_basis: str | None


class TicketResponse(ResponseModel):
    """Response model for the full appeal card.

    Attributes:
        id: Ticket identifier.
        registration_number: Business registration number.
        received_at: When the appeal was received.
        registered_at: When the appeal was registered.
        source_channel_code: Intake channel code.
        subject: Subject line.
        description: Full appeal text.
        product_code: Credit-product code.
        classifier_code: Question-classifier code.
        priority_code: Priority code.
        current_status_code: Current status (Flowable projection).
        current_stage_code: Current stage (Flowable projection).
        current_team_id: Current team, if assigned.
        current_assignee_id: Current assignee, if assigned.
        contract_number: Related contract number, if any.
        legal_due_at: Regulatory deadline, if computed.
        internal_due_at: Internal SLA deadline, if computed.
        legal_hold: Whether the ticket is under legal hold.
        is_confidential: Whether the appeal is restricted to the confidential-access role subset.
        version: Optimistic-locking version.
        applicants: The parties attached to the ticket.
    """

    id: uuid.UUID
    registration_number: str
    received_at: datetime
    registered_at: datetime
    source_channel_code: str
    subject: str
    description: str
    product_code: str
    classifier_code: str
    priority_code: str
    current_status_code: str
    current_stage_code: str
    current_team_id: uuid.UUID | None
    current_assignee_id: uuid.UUID | None
    contract_number: str | None
    legal_due_at: datetime | None
    internal_due_at: datetime | None
    sla_policy_version: str | None
    decision_code: str | None
    decision_summary: str | None
    decision_text: str | None
    decision_at: datetime | None
    decision_by: uuid.UUID | None
    closure_reason_code: str | None
    closed_at: datetime | None
    response_sent_at: datetime | None
    no_response_reason: str | None
    retention_until: date | None
    legal_hold: bool
    is_confidential: bool
    version: int
    applicants: list[ApplicantResponse]


class TicketSummary(ResponseModel):
    """Compact appeal representation for search results.

    Attributes:
        id: Ticket identifier.
        registration_number: Business registration number.
        subject: Subject line.
        current_status_code: Current status code.
        current_stage_code: Current stage code.
        product_code: Credit-product code.
        classifier_code: Question-classifier code.
        priority_code: Priority code.
        contract_number: Related contract number, if any.
        current_assignee_id: Current assignee, if assigned.
        current_team_id: Current team, if assigned.
        received_at: When the appeal was received.
        registered_at: When the appeal was registered.
    """

    id: uuid.UUID
    registration_number: str
    subject: str
    current_status_code: str
    current_stage_code: str
    product_code: str
    classifier_code: str
    priority_code: str
    contract_number: str | None
    current_assignee_id: uuid.UUID | None
    current_team_id: uuid.UUID | None
    received_at: datetime
    registered_at: datetime


class PageMeta(ResponseModel):
    """Pagination metadata.

    Attributes:
        page: 1-based page number.
        page_size: Page size.
        total: Total matching appeals.
    """

    page: int
    page_size: int
    total: int


class PaginatedTickets(ResponseModel):
    """A page of appeal search results.

    Attributes:
        items: The appeals on this page.
        page: Pagination metadata.
    """

    items: list[TicketSummary]
    page: PageMeta


class CommentResponse(ResponseModel):
    """Response model for a comment.

    Attributes:
        id: Comment identifier.
        ticket_id: Owning ticket.
        author_id: Comment author.
        body: Comment text.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime


def applicant_to_response(applicant: TicketApplicant) -> ApplicantResponse:
    """Map an applicant row to its masked response model.

    Args:
        applicant: The stored applicant.

    Returns:
        The response model with the identifier masked.
    """
    return ApplicantResponse(
        id=applicant.id,
        applicant_type=applicant.applicant_type,
        full_name=applicant.full_name,
        identifier_type=applicant.identifier_type,
        identifier_masked=mask_identifier(applicant.identifier_value),
        email=applicant.email,
        phone=applicant.phone,
        gender_code=applicant.gender_code,
        birth_date=applicant.birth_date,
        age=applicant.age,
        region_code=applicant.region_code,
        data_source=applicant.data_source,
        representative_basis=applicant.representative_basis,
    )


def ticket_to_response(ticket: Ticket) -> TicketResponse:
    """Map a ticket (with applicants loaded) to its response model.

    Args:
        ticket: The stored ticket.

    Returns:
        The full card response.
    """
    return TicketResponse(
        id=ticket.id,
        registration_number=ticket.registration_number,
        received_at=ticket.received_at,
        registered_at=ticket.registered_at,
        source_channel_code=ticket.source_channel_code,
        subject=ticket.subject,
        description=ticket.description,
        product_code=ticket.product_code,
        classifier_code=ticket.classifier_code,
        priority_code=ticket.priority_code,
        current_status_code=ticket.current_status_code,
        current_stage_code=ticket.current_stage_code,
        current_team_id=ticket.current_team_id,
        current_assignee_id=ticket.current_assignee_id,
        contract_number=ticket.contract_number,
        legal_due_at=ticket.legal_due_at,
        internal_due_at=ticket.internal_due_at,
        sla_policy_version=ticket.sla_policy_version,
        decision_code=ticket.decision_code,
        decision_summary=ticket.decision_summary,
        decision_text=ticket.decision_text,
        decision_at=ticket.decision_at,
        decision_by=ticket.decision_by,
        closure_reason_code=ticket.closure_reason_code,
        closed_at=ticket.closed_at,
        response_sent_at=ticket.response_sent_at,
        no_response_reason=ticket.no_response_reason,
        retention_until=ticket.retention_until,
        legal_hold=ticket.legal_hold,
        is_confidential=ticket.is_confidential,
        version=ticket.version,
        applicants=[applicant_to_response(a) for a in ticket.applicants],
    )


def ticket_to_summary(ticket: Ticket) -> TicketSummary:
    """Map a ticket to its search-summary model.

    Args:
        ticket: The stored ticket.

    Returns:
        The compact summary.
    """
    return TicketSummary(
        id=ticket.id,
        registration_number=ticket.registration_number,
        subject=ticket.subject,
        current_status_code=ticket.current_status_code,
        current_stage_code=ticket.current_stage_code,
        product_code=ticket.product_code,
        classifier_code=ticket.classifier_code,
        priority_code=ticket.priority_code,
        contract_number=ticket.contract_number,
        current_assignee_id=ticket.current_assignee_id,
        current_team_id=ticket.current_team_id,
        received_at=ticket.received_at,
        registered_at=ticket.registered_at,
    )


def comment_to_response(comment: TicketComment) -> CommentResponse:
    """Map a comment row to its response model.

    Args:
        comment: The stored comment.

    Returns:
        The comment response.
    """
    return CommentResponse(
        id=comment.id,
        ticket_id=comment.ticket_id,
        author_id=comment.author_id,
        body=comment.body,
        created_at=comment.created_at,
    )
