"""Tests for the decision, close, and legal-hold use cases (regulatory validation and audit)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.application.commands import (
    CloseTicketCommand,
    CreateTicketCommand,
    RecordDecisionCommand,
    SetLegalHoldCommand,
)
from ticket_service.application.events import TICKET_CLOSED, TICKET_DECISION_RECORDED
from ticket_service.application.use_cases import (
    close_ticket,
    create_manual_ticket,
    record_decision,
    set_legal_hold,
)
from ticket_service.domain.invariants import TicketInvariantError
from ticket_service.infrastructure import audit
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.models import AuditLog, OutboxEvent
from ticket_service.infrastructure.registration import RegistrationNumberAllocator


async def _register(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    caller: TicketClaims,
) -> uuid.UUID:
    """Register a ticket and return its identifier.

    Args:
        session_factory: The session factory.
        make_create_command: The command builder.
        caller: The registering caller.

    Returns:
        The registered ticket's identifier.
    """
    async with session_factory() as session:
        ticket, _ = await create_manual_ticket(
            session, RegistrationNumberAllocator("AP"), make_create_command(), caller
        )
        await session.commit()
        return ticket.id


async def _record_decision(
    session_factory: async_sessionmaker[AsyncSession],
    ticket_id: uuid.UUID,
    version: int,
    caller: TicketClaims,
) -> None:
    """Record a standard decision on a ticket.

    Args:
        session_factory: The session factory.
        ticket_id: The ticket to decide.
        version: The expected version.
        caller: The deciding caller.
    """
    async with session_factory() as session:
        await record_decision(
            session,
            RecordDecisionCommand(
                ticket_id=ticket_id,
                expected_version=version,
                decision_code="REJECTED",
                decision_text="Decision rationale",
            ),
            caller,
        )
        await session.commit()


async def test_record_decision_sets_fields_event_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Recording a decision populates the fields and stages an event and an audit entry."""
    caller = make_caller()
    ticket_id = await _register(session_factory, make_create_command, caller)

    async with session_factory() as session:
        ticket = await record_decision(
            session,
            RecordDecisionCommand(
                ticket_id=ticket_id,
                expected_version=1,
                decision_code="APPROVED",
                decision_text="Approved",
            ),
            caller,
        )
        await session.commit()
        assert ticket.decision_code == "APPROVED"
        assert ticket.decision_at is not None
        # The deciding employee is the verified caller, never client input.
        assert ticket.decision_by == caller.subject

        events = [r.event_type for r in (await session.execute(select(OutboxEvent))).scalars()]
        assert TICKET_DECISION_RECORDED in events
        actions = [r.action for r in (await session.execute(select(AuditLog))).scalars()]
        assert audit.ACTION_DECISION_RECORDED in actions


async def test_close_blocked_without_decision(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Closing without a recorded decision is rejected (docs/01)."""
    caller = make_caller()
    ticket_id = await _register(session_factory, make_create_command, caller)

    async with session_factory() as session:
        with pytest.raises(TicketInvariantError):
            await close_ticket(
                session,
                CloseTicketCommand(
                    ticket_id=ticket_id,
                    expected_version=1,
                    closure_reason_code="RESOLVED",
                    no_response_reason="No response needed",
                ),
                caller,
            )


async def test_close_blocked_without_response_or_reason(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Closing without a response date or a justified absence is rejected (docs/01)."""
    caller = make_caller()
    ticket_id = await _register(session_factory, make_create_command, caller)
    await _record_decision(session_factory, ticket_id, 1, caller)

    async with session_factory() as session:
        with pytest.raises(TicketInvariantError):
            await close_ticket(
                session,
                CloseTicketCommand(
                    ticket_id=ticket_id, expected_version=2, closure_reason_code="RESOLVED"
                ),
                caller,
            )


async def test_close_success_sets_retention_status_event_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """A valid close sets retention and terminal status, and stages an event and audit entry."""
    caller = make_caller()
    ticket_id = await _register(session_factory, make_create_command, caller)
    await _record_decision(session_factory, ticket_id, 1, caller)

    async with session_factory() as session:
        ticket = await close_ticket(
            session,
            CloseTicketCommand(
                ticket_id=ticket_id,
                expected_version=2,
                closure_reason_code="RESOLVED",
                response_sent_at=datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
            ),
            caller,
        )
        await session.commit()

        assert ticket.closed_at is not None
        assert ticket.retention_until is not None
        assert ticket.retention_until.year == ticket.closed_at.year + 5
        assert ticket.current_status_code == "COMPLETED"
        assert ticket.current_stage_code == "CLOSED"

        events = [r.event_type for r in (await session.execute(select(OutboxEvent))).scalars()]
        assert TICKET_CLOSED in events
        actions = [r.action for r in (await session.execute(select(AuditLog))).scalars()]
        assert audit.ACTION_CLOSED in actions


async def test_set_legal_hold_updates_flag_and_audits(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Setting a legal hold flips the flag and records an audit entry."""
    caller = make_caller()
    ticket_id = await _register(session_factory, make_create_command, caller)

    async with session_factory() as session:
        ticket = await set_legal_hold(
            session,
            SetLegalHoldCommand(
                ticket_id=ticket_id, expected_version=1, legal_hold=True, reason="Litigation"
            ),
            caller,
        )
        await session.commit()
        assert ticket.legal_hold is True
        actions = [r.action for r in (await session.execute(select(AuditLog))).scalars()]
        assert audit.ACTION_LEGAL_HOLD_SET in actions
