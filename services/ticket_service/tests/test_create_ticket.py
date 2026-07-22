"""Tests for the manual ticket-registration use case, including outbox events and idempotency."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.application.commands import ApplicantInput, CreateTicketCommand
from ticket_service.application.events import TICKET_CREATED
from ticket_service.application.use_cases import create_manual_ticket
from ticket_service.domain.enums import ApplicantType
from ticket_service.infrastructure.models import OutboxEvent
from ticket_service.infrastructure.outbox import envelope_from_row
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

_CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "events"


def _schema(name: str) -> dict[str, Any]:
    """Load a contract schema from the shared contracts directory.

    Args:
        name: Relative path under ``contracts/events``.

    Returns:
        The parsed schema.
    """
    return cast(dict[str, Any], json.loads((_CONTRACTS / name).read_text(encoding="utf-8")))


async def test_create_allocates_number_and_persists(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """Registration allocates a number, stores the applicants, and returns a created ticket."""
    allocator = RegistrationNumberAllocator("AP")
    async with session_factory() as session:
        ticket, created = await create_manual_ticket(session, allocator, make_create_command())
        await session.commit()

        assert created is True
        assert ticket.registration_number == "AP-2026-000001"
        assert ticket.current_status_code == "NEW"
        assert ticket.current_stage_code == "REGISTRATION"
        assert len(ticket.applicants) == 1


async def test_create_stages_valid_created_event_with_masked_identifier(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """A ticket.created.v1 event is staged, conforms to the contract, and masks the identifier."""
    allocator = RegistrationNumberAllocator("AP")
    async with session_factory() as session:
        await create_manual_ticket(session, allocator, make_create_command())
        await session.commit()

        row = (await session.execute(select(OutboxEvent))).scalar_one()

    assert row.event_type == TICKET_CREATED
    envelope = envelope_from_row(row)
    Draft202012Validator(_schema("event-envelope.v1.json")).validate(envelope)
    Draft202012Validator(_schema("payloads/ticket.created.v1.json")).validate(envelope["payload"])

    masked = envelope["payload"]["applicant"]["identifierMasked"]
    assert masked == "********0123"
    # The full identifier must never appear anywhere in the serialized event.
    assert "900101300123" not in json.dumps(envelope)


async def test_create_with_representative_flags_it(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_applicant: Callable[..., ApplicantInput],
) -> None:
    """A representative party is stored and reflected in the created event."""
    allocator = RegistrationNumberAllocator("AP")
    representative = make_applicant(
        applicant_type=ApplicantType.REPRESENTATIVE,
        full_name="Петров Петр",
        representative_basis="Power of attorney",
    )
    command = make_create_command(representative=representative)
    async with session_factory() as session:
        ticket, _ = await create_manual_ticket(session, allocator, command)
        await session.commit()
        row = (await session.execute(select(OutboxEvent))).scalar_one()

    assert len(ticket.applicants) == 2
    assert envelope_from_row(row)["payload"]["hasRepresentative"] is True


async def test_idempotent_create_returns_original_without_second_event(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """Repeating a create with the same idempotency key yields the original and no new event."""
    allocator = RegistrationNumberAllocator("AP")
    command = make_create_command(idempotency_key="key-123")

    async with session_factory() as session:
        first, first_created = await create_manual_ticket(session, allocator, command)
        await session.commit()
        first_id = first.id

    async with session_factory() as session:
        second, second_created = await create_manual_ticket(session, allocator, command)
        await session.commit()

        events = (await session.execute(select(OutboxEvent))).scalars().all()

    assert first_created is True
    assert second_created is False
    assert second.id == first_id
    assert len(events) == 1
