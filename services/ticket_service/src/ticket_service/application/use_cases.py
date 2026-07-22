"""Ticket use cases (application services).

Each use case coordinates repositories, the registration-number allocator, domain invariants, and
the transactional outbox within the caller's unit of work. Business logic lives here rather than in
API route handlers (root ``CLAUDE.md``). Use cases stage events but never commit; the API's
unit-of-work dependency owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.application import events
from ticket_service.application.commands import (
    AddCommentCommand,
    ApplicantInput,
    ClassifyTicketCommand,
    CreateTicketCommand,
    TicketSearchQuery,
    UpdateTicketCommand,
)
from ticket_service.application.errors import TicketNotFoundError, VersionConflictError
from ticket_service.domain.invariants import check_registration_fields
from ticket_service.infrastructure.models import Ticket, TicketApplicant, TicketComment
from ticket_service.infrastructure.outbox import OutboxRepository
from ticket_service.infrastructure.registration import RegistrationNumberAllocator
from ticket_service.infrastructure.repositories import CommentRepository, TicketRepository

# Initial projection codes for a freshly registered appeal. Status and stage advance only through
# the Flowable projection later (EP-3); in EP-1 they hold these placeholders (IMPLEMENTATION_PLAN).
DEFAULT_STATUS_CODE = "NEW"
DEFAULT_STAGE_CODE = "REGISTRATION"

# Card fields an update may change. Status, stage, and assignment are deliberately excluded.
_UPDATABLE_FIELDS = ("subject", "description", "source_channel_code", "contract_number")


def _to_applicant(source: ApplicantInput) -> TicketApplicant:
    """Map an applicant input to a persistent applicant row.

    Args:
        source: The applicant input.

    Returns:
        The corresponding ORM applicant (not yet associated with a ticket).
    """
    return TicketApplicant(
        applicant_type=source.applicant_type,
        data_source=source.data_source,
        full_name=source.full_name,
        identifier_type=source.identifier_type,
        identifier_value=source.identifier_value,
        email=source.email,
        phone=source.phone,
        gender_code=source.gender_code,
        birth_date=source.birth_date,
        age=source.age,
        region_code=source.region_code,
        representative_basis=source.representative_basis,
    )


async def create_manual_ticket(
    session: AsyncSession,
    allocator: RegistrationNumberAllocator,
    command: CreateTicketCommand,
) -> tuple[Ticket, bool]:
    """Register an appeal manually and stage ``ticket.created.v1``.

    When an idempotency key is supplied and a ticket already exists for it, the existing ticket is
    returned unchanged (no duplicate, no second event).

    Args:
        session: The active unit-of-work session.
        allocator: Allocator issuing the unique registration number.
        command: The registration input.

    Returns:
        A tuple of the ticket and whether it was newly created (``False`` on an idempotent hit).

    Raises:
        TicketInvariantError: If a required registration field is missing.
    """
    tickets = TicketRepository(session)
    outbox = OutboxRepository(session)

    if command.idempotency_key is not None:
        existing = await tickets.get_by_idempotency_key(command.idempotency_key)
        if existing is not None:
            return existing, False

    now = datetime.now(UTC)
    number = await allocator.allocate(session, at=now)
    ticket = Ticket(
        registration_number=number.format(),
        idempotency_key=command.idempotency_key,
        received_at=command.received_at,
        registered_at=now,
        source_channel_code=command.source_channel_code,
        subject=command.subject,
        description=command.description,
        contract_number=command.contract_number,
        product_code=command.product_code,
        classifier_code=command.classifier_code,
        priority_code=command.priority_code,
        current_status_code=DEFAULT_STATUS_CODE,
        current_stage_code=DEFAULT_STAGE_CODE,
    )
    check_registration_fields(
        {
            "registration_number": ticket.registration_number,
            "received_at": ticket.received_at,
            "registered_at": ticket.registered_at,
            "source_channel_code": ticket.source_channel_code,
            "subject": ticket.subject,
            "description": ticket.description,
            "product_code": ticket.product_code,
            "classifier_code": ticket.classifier_code,
            "priority_code": ticket.priority_code,
            "current_status_code": ticket.current_status_code,
            "current_stage_code": ticket.current_stage_code,
        }
    )

    consumer = _to_applicant(command.applicant)
    ticket.applicants.append(consumer)
    if command.representative is not None:
        ticket.applicants.append(_to_applicant(command.representative))

    tickets.add(ticket)
    await session.flush()

    await outbox.enqueue(
        events.ticket_created_event(ticket, consumer, command.representative is not None)
    )
    return ticket, True


async def update_ticket_details(session: AsyncSession, command: UpdateTicketCommand) -> Ticket:
    """Update editable appeal-card fields and stage ``ticket.updated.v1``.

    Args:
        session: The active unit-of-work session.
        command: The update input (only provided fields are applied).

    Returns:
        The updated ticket.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)

    changed: list[str] = []
    for name in _UPDATABLE_FIELDS:
        if name not in command.provided:
            continue
        new_value = getattr(command, name)
        if getattr(ticket, name) != new_value:
            setattr(ticket, name, new_value)
            changed.append(name)

    if not changed:
        return ticket

    await session.flush()
    await OutboxRepository(session).enqueue(events.ticket_updated_event(ticket.id, changed))
    return ticket


async def classify_ticket(session: AsyncSession, command: ClassifyTicketCommand) -> Ticket:
    """Set an appeal's classification and stage ``ticket.classified.v1``.

    Args:
        session: The active unit-of-work session.
        command: The classification input.

    Returns:
        The reclassified ticket.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)
    ticket.product_code = command.product_code
    ticket.classifier_code = command.classifier_code
    ticket.priority_code = command.priority_code
    await session.flush()
    await OutboxRepository(session).enqueue(events.ticket_classified_event(ticket))
    return ticket


async def get_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket:
    """Load an appeal card by identifier.

    Args:
        session: The active session.
        ticket_id: The ticket identifier.

    Returns:
        The ticket with its applicants.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
    """
    ticket = await TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise TicketNotFoundError(str(ticket_id))
    return ticket


async def add_comment(session: AsyncSession, command: AddCommentCommand) -> TicketComment:
    """Add a comment to an appeal.

    Args:
        session: The active unit-of-work session.
        command: The comment input.

    Returns:
        The created comment.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
    """
    tickets = TicketRepository(session)
    if await tickets.get(command.ticket_id) is None:
        raise TicketNotFoundError(str(command.ticket_id))

    comment = TicketComment(
        ticket_id=command.ticket_id, author_id=command.author_id, body=command.body
    )
    CommentRepository(session).add(comment)
    await session.flush()
    return comment


async def list_comments(session: AsyncSession, ticket_id: uuid.UUID) -> Sequence[TicketComment]:
    """List an appeal's comments, verifying the appeal exists.

    Args:
        session: The active session.
        ticket_id: The owning ticket identifier.

    Returns:
        The comments ordered newest first.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
    """
    tickets = TicketRepository(session)
    if await tickets.get(ticket_id) is None:
        raise TicketNotFoundError(str(ticket_id))
    return await CommentRepository(session).list_for_ticket(ticket_id)


async def search_tickets(
    session: AsyncSession, query: TicketSearchQuery
) -> tuple[Sequence[Ticket], int]:
    """Search appeals by the supported filters.

    Args:
        session: The active session.
        query: The search filters and pagination.

    Returns:
        A tuple of the page's tickets and the total match count.
    """
    return await TicketRepository(session).search(query)


async def _load_for_write(
    session: AsyncSession, ticket_id: uuid.UUID, expected_version: int
) -> Ticket:
    """Load a ticket for modification, enforcing existence and optimistic locking.

    Args:
        session: The active session.
        ticket_id: The ticket identifier.
        expected_version: The version the client last observed.

    Returns:
        The ticket ready for modification.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If the stored version differs from ``expected_version``.
    """
    ticket = await TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise TicketNotFoundError(str(ticket_id))
    if ticket.version != expected_version:
        raise VersionConflictError(expected_version, ticket.version)
    return ticket
