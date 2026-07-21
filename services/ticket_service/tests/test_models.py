"""Persistence-level invariant tests for the ticket models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from ticket_service.domain.enums import ApplicantType, DataSource
from ticket_service.infrastructure.models import Ticket, TicketApplicant


def _ticket_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build keyword arguments for a valid ticket, applying overrides.

    Args:
        **overrides: Field values to replace or remove (set to ``None``) in the base set.

    Returns:
        A mapping suitable for ``Ticket(**kwargs)``.
    """
    now = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)
    base: dict[str, Any] = {
        "registration_number": "AP-2026-000001",
        "received_at": now,
        "registered_at": now,
        "source_channel_code": "EMAIL",
        "subject": "Restructuring request",
        "description": "Full appeal text",
        "product_code": "MICROLOAN",
        "classifier_code": "RESTRUCTURING",
        "priority_code": "NORMAL",
        "current_status_code": "NEW",
        "current_stage_code": "REGISTRATION",
    }
    base.update(overrides)
    return base


async def test_ticket_persists_with_optional_fields_absent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A ticket registers with all conditional/nullable fields left unset."""
    async with session_factory() as session:
        ticket = Ticket(**_ticket_kwargs())
        session.add(ticket)
        await session.commit()

        stored = (await session.execute(select(Ticket))).scalar_one()
        assert stored.decision_code is None
        assert stored.closed_at is None
        assert stored.retention_until is None
        assert stored.legal_hold is False
        assert stored.version == 1


async def test_applicant_persists_with_only_type_and_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Demographic fields are nullable; an applicant needs only its type and data source."""
    async with session_factory() as session:
        ticket = Ticket(**_ticket_kwargs())
        ticket.applicants.append(
            TicketApplicant(
                applicant_type=ApplicantType.CONSUMER,
                data_source=DataSource.APPEAL,
            )
        )
        session.add(ticket)
        await session.commit()

        stored = (await session.execute(select(TicketApplicant))).scalar_one()
        assert stored.applicant_type is ApplicantType.CONSUMER
        assert stored.identifier_value is None
        assert stored.gender_code is None
        assert stored.region_code is None


async def test_registration_number_is_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two tickets cannot share a registration number."""
    async with session_factory() as session:
        session.add(Ticket(**_ticket_kwargs()))
        await session.commit()

    async with session_factory() as session:
        session.add(Ticket(**_ticket_kwargs()))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_missing_required_field_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A NULL in a required column is rejected by the database."""
    async with session_factory() as session:
        session.add(Ticket(**_ticket_kwargs(subject=None)))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_optimistic_locking_detects_concurrent_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A stale update loses to the winning writer and raises StaleDataError."""
    async with session_factory() as session:
        session.add(Ticket(**_ticket_kwargs()))
        await session.commit()

    async with session_factory() as session_a, session_factory() as session_b:
        ticket_a = (await session_a.execute(select(Ticket))).scalar_one()
        ticket_b = (await session_b.execute(select(Ticket))).scalar_one()

        ticket_a.subject = "Updated by A"
        await session_a.commit()

        ticket_b.subject = "Updated by B"
        with pytest.raises(StaleDataError):
            await session_b.commit()
