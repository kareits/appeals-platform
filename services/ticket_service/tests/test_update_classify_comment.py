"""Tests for the update, classify, and comment use cases."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.application.commands import (
    AddCommentCommand,
    ClassifyTicketCommand,
    CreateTicketCommand,
    UpdateTicketCommand,
)
from ticket_service.application.errors import TicketNotFoundError, VersionConflictError
from ticket_service.application.events import TICKET_CLASSIFIED, TICKET_UPDATED
from ticket_service.application.use_cases import (
    add_comment,
    classify_ticket,
    create_manual_ticket,
    list_comments,
    update_ticket_details,
)
from ticket_service.infrastructure.models import OutboxEvent
from ticket_service.infrastructure.registration import RegistrationNumberAllocator


async def _create(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> uuid.UUID:
    """Create a ticket and return its identifier.

    Args:
        session_factory: The session factory.
        make_create_command: The command builder.

    Returns:
        The created ticket's identifier.
    """
    async with session_factory() as session:
        ticket, _ = await create_manual_ticket(
            session, RegistrationNumberAllocator("AP"), make_create_command()
        )
        await session.commit()
        return ticket.id


async def _pending_event_types(session: AsyncSession) -> list[str]:
    """Return the event types currently staged in the outbox.

    Args:
        session: The active session.

    Returns:
        The list of staged event types.
    """
    rows = (await session.execute(select(OutboxEvent))).scalars().all()
    return [row.event_type for row in rows]


async def test_update_changes_fields_and_emits_event(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """Updating a field bumps the version and stages a ticket.updated.v1 with the changed field."""
    ticket_id = await _create(session_factory, make_create_command)

    async with session_factory() as session:
        ticket = await update_ticket_details(
            session,
            UpdateTicketCommand(
                ticket_id=ticket_id,
                expected_version=1,
                subject="Updated subject",
                provided=frozenset({"subject"}),
            ),
        )
        await session.commit()
        assert ticket.subject == "Updated subject"
        assert ticket.version == 2

        rows = (await session.execute(select(OutboxEvent))).scalars().all()
        updated = [r for r in rows if r.event_type == TICKET_UPDATED]
        assert len(updated) == 1
        assert updated[0].payload["changedFields"] == ["subject"]


async def test_update_without_changes_emits_no_event(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """Providing the same value as stored changes nothing and stages no update event."""
    ticket_id = await _create(session_factory, make_create_command)

    async with session_factory() as session:
        await update_ticket_details(
            session,
            UpdateTicketCommand(
                ticket_id=ticket_id,
                expected_version=1,
                subject="Restructuring request",
                provided=frozenset({"subject"}),
            ),
        )
        await session.commit()
        assert TICKET_UPDATED not in await _pending_event_types(session)


async def test_update_version_conflict(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """A stale expected version is rejected."""
    ticket_id = await _create(session_factory, make_create_command)

    async with session_factory() as session:
        with pytest.raises(VersionConflictError):
            await update_ticket_details(
                session,
                UpdateTicketCommand(
                    ticket_id=ticket_id,
                    expected_version=99,
                    subject="X",
                    provided=frozenset({"subject"}),
                ),
            )


async def test_classify_sets_codes_and_emits_event(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """Classifying sets the codes and stages ticket.classified.v1."""
    ticket_id = await _create(session_factory, make_create_command)

    async with session_factory() as session:
        ticket = await classify_ticket(
            session,
            ClassifyTicketCommand(
                ticket_id=ticket_id,
                expected_version=1,
                product_code="INSTALLMENT",
                classifier_code="COMPLAINT",
                priority_code="HIGH",
            ),
        )
        await session.commit()
        assert ticket.classifier_code == "COMPLAINT"
        assert ticket.priority_code == "HIGH"
        assert TICKET_CLASSIFIED in await _pending_event_types(session)


async def test_add_and_list_comments(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """A comment can be added and then listed."""
    ticket_id = await _create(session_factory, make_create_command)
    author = uuid.uuid4()

    async with session_factory() as session:
        await add_comment(
            session, AddCommentCommand(ticket_id=ticket_id, author_id=author, body="Note")
        )
        await session.commit()

    async with session_factory() as session:
        comments = await list_comments(session, ticket_id)
        assert len(comments) == 1
        assert comments[0].body == "Note"
        assert comments[0].author_id == author


async def test_comment_on_missing_ticket_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Commenting on a non-existent ticket raises not-found."""
    async with session_factory() as session:
        with pytest.raises(TicketNotFoundError):
            await add_comment(
                session,
                AddCommentCommand(ticket_id=uuid.uuid4(), author_id=uuid.uuid4(), body="x"),
            )
