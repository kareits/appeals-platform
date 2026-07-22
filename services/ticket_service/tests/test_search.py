"""Tests for the ticket search use case across all supported filters."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.application.commands import CreateTicketCommand, TicketSearchQuery
from ticket_service.application.use_cases import create_manual_ticket, search_tickets
from ticket_service.domain.enums import IdentifierType
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

_ASSIGNEE = uuid.uuid4()
_TEAM = uuid.uuid4()


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_applicant: Callable[..., object],
) -> None:
    """Create a small, varied set of tickets for search assertions.

    Args:
        session_factory: The session factory.
        make_create_command: The command builder.
        make_applicant: The applicant builder.
    """
    allocator = RegistrationNumberAllocator("AP")
    commands = [
        make_create_command(
            source_channel_code="EMAIL",
            product_code="MICROLOAN",
            classifier_code="RESTRUCTURING",
            contract_number="C-1",
            received_at=datetime(2026, 7, 1, tzinfo=UTC),
            applicant=make_applicant(full_name="Иванов Иван", identifier_value="900101300123"),
        ),
        make_create_command(
            source_channel_code="PAPER",
            product_code="INSTALLMENT",
            classifier_code="COMPLAINT",
            contract_number="C-2",
            received_at=datetime(2026, 7, 10, tzinfo=UTC),
            applicant=make_applicant(
                full_name="ТОО Ромашка",
                identifier_type=IdentifierType.BIN,
                identifier_value="123456789012",
            ),
        ),
        make_create_command(
            source_channel_code="PORTAL",
            product_code="MICROLOAN",
            classifier_code="INFO_REQUEST",
            contract_number=None,
            received_at=datetime(2026, 7, 20, tzinfo=UTC),
            applicant=make_applicant(full_name="Сидоров Семен", identifier_value="800202400234"),
        ),
    ]
    async with session_factory() as session:
        created = []
        for command in commands:
            ticket, _ = await create_manual_ticket(session, allocator, command)
            created.append(ticket)
        # Simulate a Flowable projection assigning the first ticket and moving the second.
        created[0].current_assignee_id = _ASSIGNEE
        created[0].current_team_id = _TEAM
        created[1].current_status_code = "IN_PROGRESS"
        await session.commit()


async def test_search_by_each_filter(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_applicant: Callable[..., object],
) -> None:
    """Each supported filter narrows the result set as expected."""
    await _seed(session_factory, make_create_command, make_applicant)

    async with session_factory() as session:

        async def count(query: TicketSearchQuery) -> int:
            """Run a search and return the total match count.

            Args:
                query: The search query.

            Returns:
                The total number of matches.
            """
            _, total = await search_tickets(session, query)
            return total

        assert await count(TicketSearchQuery(identifier_value="900101300123")) == 1
        assert await count(TicketSearchQuery(identifier_value="123456789012")) == 1
        # Partial substring match. Case-insensitivity for Cyrillic relies on the PostgreSQL
        # ILIKE collation in production; SQLite LIKE folds ASCII only, so match the stored case.
        assert await count(TicketSearchQuery(full_name="Иванов")) == 1
        assert await count(TicketSearchQuery(contract_number="C-2")) == 1
        assert await count(TicketSearchQuery(product_code="MICROLOAN")) == 2
        assert await count(TicketSearchQuery(classifier_code="COMPLAINT")) == 1
        assert await count(TicketSearchQuery(channel_code="PORTAL")) == 1
        assert await count(TicketSearchQuery(status_code="IN_PROGRESS")) == 1
        assert await count(TicketSearchQuery(stage_code="REGISTRATION")) == 3
        assert await count(TicketSearchQuery(assignee_id=_ASSIGNEE)) == 1
        assert await count(TicketSearchQuery(team_id=_TEAM)) == 1
        assert await count(TicketSearchQuery(received_from=datetime(2026, 7, 5, tzinfo=UTC))) == 2
        assert await count(TicketSearchQuery(received_to=datetime(2026, 7, 5, tzinfo=UTC))) == 1


async def test_search_by_registration_number(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_applicant: Callable[..., object],
) -> None:
    """An exact registration-number filter returns the single matching ticket."""
    await _seed(session_factory, make_create_command, make_applicant)

    async with session_factory() as session:
        tickets, total = await search_tickets(
            session, TicketSearchQuery(registration_number="AP-2026-000002")
        )
        assert total == 1
        assert tickets[0].registration_number == "AP-2026-000002"


async def test_search_pagination(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_applicant: Callable[..., object],
) -> None:
    """Pagination limits the page while reporting the full total."""
    await _seed(session_factory, make_create_command, make_applicant)

    async with session_factory() as session:
        page1, total = await search_tickets(session, TicketSearchQuery(page=1, page_size=2))
        page2, _ = await search_tickets(session, TicketSearchQuery(page=2, page_size=2))

    assert total == 3
    assert len(page1) == 2
    assert len(page2) == 1
