"""HTTP routes for the ticket API.

Handlers are thin: they translate requests into command/query DTOs, invoke the application use
cases, commit the unit of work, and map results (and domain errors) to responses. No business
logic lives here (root ``CLAUDE.md``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import tzinfo
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from mfo_http import ProblemDetail, ProblemDetailError
from pydantic import AwareDatetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from ticket_service.api.dependencies import get_allocator, get_platform_timezone, get_session
from ticket_service.api.schemas import (
    ApplicantModel,
    ClassifyRequest,
    CloseTicketRequest,
    CommentRequest,
    CommentResponse,
    CreateTicketRequest,
    LegalHoldRequest,
    PageMeta,
    PaginatedTickets,
    RecordDecisionRequest,
    TicketResponse,
    UpdateTicketRequest,
    comment_to_response,
    ticket_to_response,
    ticket_to_summary,
)
from ticket_service.application import use_cases
from ticket_service.application.commands import (
    AddCommentCommand,
    ApplicantInput,
    ClassifyTicketCommand,
    CloseTicketCommand,
    CreateTicketCommand,
    RecordDecisionCommand,
    SetLegalHoldCommand,
    TicketSearchQuery,
    UpdateTicketCommand,
)
from ticket_service.application.errors import (
    TicketNotFoundError,
    UnknownReferenceCodeError,
    VersionConflictError,
)
from ticket_service.domain.invariants import TicketInvariantError
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

router = APIRouter(prefix="/api/v1", tags=["tickets"])

_UPDATABLE_FIELDS = frozenset({"subject", "description", "source_channel_code", "contract_number"})


@asynccontextmanager
async def _domain_errors() -> AsyncIterator[None]:
    """Translate application/domain errors into RFC 7807 Problem Details.

    Yields:
        Control to the wrapped block; exceptions are converted to :class:`ProblemDetailError`.

    Raises:
        ProblemDetailError: For not-found (404), version/integrity conflicts (409), and invariant
            violations (422).
    """
    try:
        yield
    except TicketNotFoundError as exc:
        raise _problem(404, "Ticket not found", str(exc)) from exc
    except VersionConflictError as exc:
        raise _problem(409, "Version conflict", str(exc)) from exc
    except StaleDataError as exc:
        raise _problem(409, "Version conflict", "the ticket was modified concurrently") from exc
    except IntegrityError as exc:
        raise _problem(409, "Conflict", "the request conflicts with an existing record") from exc
    except UnknownReferenceCodeError as exc:
        raise _problem(422, "Invalid reference code", str(exc)) from exc
    except TicketInvariantError as exc:
        raise _problem(422, "Invalid ticket", str(exc)) from exc


def _problem(status: int, title: str, detail: str | None = None) -> ProblemDetailError:
    """Build a Problem Details error.

    Args:
        status: HTTP status code.
        title: Short problem title.
        detail: Optional occurrence-specific detail.

    Returns:
        The error to raise.
    """
    return ProblemDetailError(ProblemDetail(title=title, status=status, detail=detail))


def _to_applicant_input(model: ApplicantModel) -> ApplicantInput:
    """Map an applicant request model to an applicant command input.

    Args:
        model: The request applicant.

    Returns:
        The command input.
    """
    return ApplicantInput(
        applicant_type=model.applicant_type,
        data_source=model.data_source,
        full_name=model.full_name,
        identifier_type=model.identifier_type,
        identifier_value=model.identifier_value,
        email=model.email,
        phone=model.phone,
        gender_code=model.gender_code,
        birth_date=model.birth_date,
        age=model.age,
        region_code=model.region_code,
        representative_basis=model.representative_basis,
    )


@router.post(
    "/tickets", response_model=TicketResponse, status_code=201, operation_id="createManualTicket"
)
async def create_manual_ticket(
    body: CreateTicketRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    allocator: Annotated[RegistrationNumberAllocator, Depends(get_allocator)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> TicketResponse:
    """Register an appeal manually.

    Args:
        body: The registration request.
        response: The response object, used to signal an idempotent hit with HTTP 200.
        session: The unit-of-work session.
        allocator: The registration-number allocator.
        idempotency_key: Optional key making the create retry-safe.

    Returns:
        The registered (or previously registered) appeal card.
    """
    command = CreateTicketCommand(
        received_at=body.received_at,
        source_channel_code=body.source_channel_code,
        subject=body.subject,
        description=body.description,
        product_code=body.product_code,
        classifier_code=body.classifier_code,
        priority_code=body.priority_code,
        applicant=_to_applicant_input(body.applicant),
        contract_number=body.contract_number,
        representative=(
            _to_applicant_input(body.representative) if body.representative is not None else None
        ),
        idempotency_key=idempotency_key,
    )
    async with _domain_errors():
        ticket, created = await use_cases.create_manual_ticket(session, allocator, command)
        await session.commit()
    if not created:
        response.status_code = 200
    return ticket_to_response(ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketResponse, operation_id="getTicket")
async def get_ticket(
    ticket_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketResponse:
    """Return an appeal card by identifier.

    Args:
        ticket_id: The ticket identifier.
        session: The database session.

    Returns:
        The appeal card.
    """
    async with _domain_errors():
        ticket = await use_cases.get_ticket(session, ticket_id)
    return ticket_to_response(ticket)


@router.get("/tickets", response_model=PaginatedTickets, operation_id="searchTickets")
async def search_tickets(
    session: Annotated[AsyncSession, Depends(get_session)],
    registration_number: Annotated[str | None, Query(alias="registrationNumber")] = None,
    identifier_value: Annotated[str | None, Query(alias="identifierValue")] = None,
    full_name: Annotated[str | None, Query(alias="fullName")] = None,
    contract_number: Annotated[str | None, Query(alias="contractNumber")] = None,
    status_code: Annotated[str | None, Query(alias="statusCode")] = None,
    stage_code: Annotated[str | None, Query(alias="stageCode")] = None,
    product_code: Annotated[str | None, Query(alias="productCode")] = None,
    classifier_code: Annotated[str | None, Query(alias="classifierCode")] = None,
    channel_code: Annotated[str | None, Query(alias="channelCode")] = None,
    assignee_id: Annotated[uuid.UUID | None, Query(alias="assigneeId")] = None,
    team_id: Annotated[uuid.UUID | None, Query(alias="teamId")] = None,
    received_from: Annotated[AwareDatetime | None, Query(alias="receivedFrom")] = None,
    received_to: Annotated[AwareDatetime | None, Query(alias="receivedTo")] = None,
    registered_from: Annotated[AwareDatetime | None, Query(alias="registeredFrom")] = None,
    registered_to: Annotated[AwareDatetime | None, Query(alias="registeredTo")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> PaginatedTickets:
    """Search appeals by the supported filters.

    Args:
        session: The database session.
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
        received_from: Inclusive lower bound on receivedAt.
        received_to: Inclusive upper bound on receivedAt.
        registered_from: Inclusive lower bound on registeredAt.
        registered_to: Inclusive upper bound on registeredAt.
        page: 1-based page number.
        page_size: Page size.

    Returns:
        A page of matching appeals.
    """
    query = TicketSearchQuery(
        registration_number=registration_number,
        identifier_value=identifier_value,
        full_name=full_name,
        contract_number=contract_number,
        status_code=status_code,
        stage_code=stage_code,
        product_code=product_code,
        classifier_code=classifier_code,
        channel_code=channel_code,
        assignee_id=assignee_id,
        team_id=team_id,
        received_from=received_from,
        received_to=received_to,
        registered_from=registered_from,
        registered_to=registered_to,
        page=page,
        page_size=page_size,
    )
    tickets, total = await use_cases.search_tickets(session, query)
    return PaginatedTickets(
        items=[ticket_to_summary(t) for t in tickets],
        page=PageMeta(page=page, page_size=page_size, total=total),
    )


@router.patch(
    "/tickets/{ticket_id}", response_model=TicketResponse, operation_id="updateTicketDetails"
)
async def update_ticket_details(
    ticket_id: uuid.UUID,
    body: UpdateTicketRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketResponse:
    """Update editable appeal-card details.

    Args:
        ticket_id: The ticket identifier.
        body: The partial update request.
        session: The unit-of-work session.

    Returns:
        The updated appeal card.
    """
    provided = frozenset(body.model_fields_set) & _UPDATABLE_FIELDS
    command = UpdateTicketCommand(
        ticket_id=ticket_id,
        expected_version=body.expected_version,
        subject=body.subject,
        description=body.description,
        source_channel_code=body.source_channel_code,
        contract_number=body.contract_number,
        provided=provided,
    )
    async with _domain_errors():
        ticket = await use_cases.update_ticket_details(session, command)
        await session.commit()
    return ticket_to_response(ticket)


@router.post(
    "/tickets/{ticket_id}/classify", response_model=TicketResponse, operation_id="classifyTicket"
)
async def classify_ticket(
    ticket_id: uuid.UUID,
    body: ClassifyRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketResponse:
    """Set an appeal's classification.

    Args:
        ticket_id: The ticket identifier.
        body: The classification request.
        session: The unit-of-work session.

    Returns:
        The reclassified appeal card.
    """
    command = ClassifyTicketCommand(
        ticket_id=ticket_id,
        expected_version=body.expected_version,
        product_code=body.product_code,
        classifier_code=body.classifier_code,
        priority_code=body.priority_code,
    )
    async with _domain_errors():
        ticket = await use_cases.classify_ticket(session, command)
        await session.commit()
    return ticket_to_response(ticket)


@router.post(
    "/tickets/{ticket_id}/decision", response_model=TicketResponse, operation_id="recordDecision"
)
async def record_decision(
    ticket_id: uuid.UUID,
    body: RecordDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketResponse:
    """Record the decision on an appeal.

    Args:
        ticket_id: The ticket identifier.
        body: The decision request.
        session: The unit-of-work session.

    Returns:
        The appeal card with the recorded decision.
    """
    command = RecordDecisionCommand(
        ticket_id=ticket_id,
        expected_version=body.expected_version,
        decision_code=body.decision_code,
        decision_text=body.decision_text,
        decision_by=body.decision_by,
        decision_summary=body.decision_summary,
    )
    async with _domain_errors():
        ticket = await use_cases.record_decision(session, command)
        await session.commit()
    return ticket_to_response(ticket)


@router.post(
    "/tickets/{ticket_id}/close", response_model=TicketResponse, operation_id="closeTicket"
)
async def close_ticket(
    ticket_id: uuid.UUID,
    body: CloseTicketRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    timezone: Annotated[tzinfo, Depends(get_platform_timezone)],
) -> TicketResponse:
    """Close an appeal after validating the regulatory prerequisites.

    Args:
        ticket_id: The ticket identifier.
        body: The closure request.
        session: The unit-of-work session.
        timezone: The business timezone used for the retention date.

    Returns:
        The closed appeal card.
    """
    command = CloseTicketCommand(
        ticket_id=ticket_id,
        expected_version=body.expected_version,
        closure_reason_code=body.closure_reason_code,
        response_sent_at=body.response_sent_at,
        no_response_reason=body.no_response_reason,
        actor_id=body.actor_id,
    )
    async with _domain_errors():
        ticket = await use_cases.close_ticket(session, command, timezone)
        await session.commit()
    return ticket_to_response(ticket)


@router.post(
    "/tickets/{ticket_id}/legal-hold", response_model=TicketResponse, operation_id="setLegalHold"
)
async def set_legal_hold(
    ticket_id: uuid.UUID,
    body: LegalHoldRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketResponse:
    """Set or clear the legal hold on an appeal.

    Args:
        ticket_id: The ticket identifier.
        body: The legal-hold request.
        session: The unit-of-work session.

    Returns:
        The appeal card with the updated legal-hold flag.
    """
    command = SetLegalHoldCommand(
        ticket_id=ticket_id,
        expected_version=body.expected_version,
        legal_hold=body.legal_hold,
        reason=body.reason,
        actor_id=body.actor_id,
    )
    async with _domain_errors():
        ticket = await use_cases.set_legal_hold(session, command)
        await session.commit()
    return ticket_to_response(ticket)


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=201,
    operation_id="addComment",
)
async def add_comment(
    ticket_id: uuid.UUID,
    body: CommentRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommentResponse:
    """Add a comment to an appeal.

    Args:
        ticket_id: The ticket identifier.
        body: The comment request.
        session: The unit-of-work session.

    Returns:
        The created comment.
    """
    command = AddCommentCommand(ticket_id=ticket_id, author_id=body.author_id, body=body.body)
    async with _domain_errors():
        comment = await use_cases.add_comment(session, command)
        await session.commit()
    return comment_to_response(comment)


@router.get(
    "/tickets/{ticket_id}/comments",
    response_model=list[CommentResponse],
    operation_id="listComments",
)
async def list_comments(
    ticket_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CommentResponse]:
    """List an appeal's comments, newest first.

    Args:
        ticket_id: The ticket identifier.
        session: The database session.

    Returns:
        The comments attached to the appeal.
    """
    async with _domain_errors():
        comments = await use_cases.list_comments(session, ticket_id)
    return [comment_to_response(c) for c in comments]
