"""Tests for the manual ticket-registration use case, including outbox events and idempotency."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.application.commands import ApplicantInput, CreateTicketCommand
from ticket_service.application.errors import LegacyIdempotencyError
from ticket_service.application.events import TICKET_CREATED
from ticket_service.application.use_cases import (
    _request_fingerprint,
    _scoped_idempotency_key,
    create_manual_ticket,
)
from ticket_service.domain.enums import ApplicantType
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.models import OutboxEvent, Ticket
from ticket_service.infrastructure.outbox import envelope_from_row
from ticket_service.infrastructure.registration import RegistrationNumberAllocator
from ticket_service.infrastructure.repositories import TicketRepository

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
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Registration allocates a number, stores the applicants, and returns a created ticket."""
    allocator = RegistrationNumberAllocator("AP")
    async with session_factory() as session:
        ticket, created = await create_manual_ticket(
            session, allocator, make_create_command(), make_caller()
        )
        await session.commit()

        assert created is True
        assert ticket.registration_number == "AP-2026-000001"
        assert ticket.current_status_code == "NEW"
        assert ticket.current_stage_code == "REGISTRATION"
        assert len(ticket.applicants) == 1


async def test_create_stages_valid_created_event_with_masked_identifier(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """A ticket.created.v1 event is staged, conforms to the contract, and masks the identifier."""
    allocator = RegistrationNumberAllocator("AP")
    async with session_factory() as session:
        await create_manual_ticket(session, allocator, make_create_command(), make_caller())
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
    make_caller: Callable[..., TicketClaims],
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
        ticket, _ = await create_manual_ticket(session, allocator, command, make_caller())
        await session.commit()
        row = (await session.execute(select(OutboxEvent))).scalar_one()

    assert len(ticket.applicants) == 2
    assert envelope_from_row(row)["payload"]["hasRepresentative"] is True


async def test_legacy_idempotency_key_is_refused_not_duplicated(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """A retry of a pre-upgrade (raw key, NULL fingerprint) request is 409, not a duplicate."""
    now = datetime(2026, 7, 1, tzinfo=UTC)
    async with session_factory() as session:
        # A legacy row as written before per-caller idempotency scoping: raw key, no fingerprint.
        session.add(
            Ticket(
                registration_number="AP-2026-000001",
                idempotency_key="legacy-key",
                idempotency_fingerprint=None,
                received_at=now,
                registered_at=now,
                source_channel_code="EMAIL",
                subject="Legacy appeal",
                description="Body",
                product_code="MICROLOAN",
                classifier_code="RESTRUCTURING",
                priority_code="NORMAL",
                current_status_code="NEW",
                current_stage_code="REGISTRATION",
                is_confidential=False,
                legal_hold=False,
                version=1,
            )
        )
        await session.commit()

    allocator = RegistrationNumberAllocator("AP")
    async with session_factory() as session:
        with pytest.raises(LegacyIdempotencyError):
            await create_manual_ticket(
                session, allocator, make_create_command(idempotency_key="legacy-key"), make_caller()
            )

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Ticket))
    assert count == 1  # no duplicate regulatory record was created


def _persisted_ticket(*, idempotency_key: str, fingerprint: str) -> Ticket:
    """Build a minimal persisted ticket carrying a scoped idempotency key and fingerprint.

    Args:
        idempotency_key: The stored (scoped) idempotency key.
        fingerprint: The stored request fingerprint.

    Returns:
        A ticket row suitable for direct insertion.
    """
    now = datetime(2026, 7, 1, tzinfo=UTC)
    return Ticket(
        registration_number="AP-2026-000001",
        idempotency_key=idempotency_key,
        idempotency_fingerprint=fingerprint,
        received_at=now,
        registered_at=now,
        source_channel_code="EMAIL",
        subject="Race winner",
        description="Body",
        product_code="MICROLOAN",
        classifier_code="RESTRUCTURING",
        priority_code="NORMAL",
        current_status_code="NEW",
        current_stage_code="REGISTRATION",
        is_confidential=False,
        legal_hold=False,
        version=1,
    )


async def test_concurrent_idempotency_recovery_returns_original(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
    monkeypatch: Any,
) -> None:
    """A concurrent duplicate (insert conflict) returns the original, not a second record."""
    caller = make_caller()
    command = make_create_command(idempotency_key="race-key")
    scoped = _scoped_idempotency_key(caller.subject, "race-key")
    fingerprint = _request_fingerprint(command)

    async with session_factory() as session:
        session.add(_persisted_ticket(idempotency_key=scoped, fingerprint=fingerprint))
        await session.commit()
        winner_id = (await session.execute(select(Ticket.id))).scalar_one()

    # Simulate the concurrency window: the fast-path lookup misses (the concurrent winner is not yet
    # visible), so the insert conflicts and the IntegrityError recovery path runs.
    real_lookup = TicketRepository.get_by_idempotency_key
    calls = {"n": 0}

    async def _flaky_lookup(self: TicketRepository, key: str) -> Ticket | None:
        """Return None on the first (fast-path) call, then defer to the real lookup.

        Args:
            self: The repository instance.
            key: The idempotency key.

        Returns:
            ``None`` on the first call, otherwise the real lookup result.
        """
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return await real_lookup(self, key)

    monkeypatch.setattr(TicketRepository, "get_by_idempotency_key", _flaky_lookup)

    async with session_factory() as session:
        ticket, created = await create_manual_ticket(
            session, RegistrationNumberAllocator("AP"), command, caller
        )
        await session.commit()

    assert created is False
    assert ticket.id == winner_id

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Ticket))
    assert count == 1  # the conflicting insert did not create a duplicate


async def test_idempotent_create_returns_original_without_second_event(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Repeating a create with the same idempotency key yields the original and no new event."""
    allocator = RegistrationNumberAllocator("AP")
    command = make_create_command(idempotency_key="key-123")

    async with session_factory() as session:
        first, first_created = await create_manual_ticket(
            session, allocator, command, make_caller()
        )
        await session.commit()
        first_id = first.id

    async with session_factory() as session:
        second, second_created = await create_manual_ticket(
            session, allocator, command, make_caller()
        )
        await session.commit()

        events = (await session.execute(select(OutboxEvent))).scalars().all()

    assert first_created is True
    assert second_created is False
    assert second.id == first_id
    assert len(events) == 1
