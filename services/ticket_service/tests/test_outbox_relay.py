"""Tests for the transactional-outbox relay."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.application.commands import CreateTicketCommand
from ticket_service.application.use_cases import create_manual_ticket
from ticket_service.infrastructure.models import OutboxEvent
from ticket_service.infrastructure.outbox import OutboxRelay
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

_ENVELOPE_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[3] / "contracts" / "events" / "event-envelope.v1.json"
    ).read_text(encoding="utf-8")
)


class CollectingPublisher:
    """Test publisher that records and schema-validates every envelope it receives."""

    def __init__(self) -> None:
        """Initialize with an empty capture list."""
        self.published: list[dict[str, Any]] = []

    async def publish(self, envelope: dict[str, Any]) -> None:
        """Validate and record a published envelope.

        Args:
            envelope: The event envelope to publish.
        """
        Draft202012Validator(cast(dict[str, Any], _ENVELOPE_SCHEMA)).validate(envelope)
        self.published.append(envelope)


async def _seed_two_events(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """Stage two ticket.created events by registering two tickets.

    Args:
        session_factory: The session factory.
        make_create_command: The command builder.
    """
    allocator = RegistrationNumberAllocator("AP")
    async with session_factory() as session:
        await create_manual_ticket(session, allocator, make_create_command())
        await create_manual_ticket(session, allocator, make_create_command())
        await session.commit()


async def test_relay_publishes_and_marks_events(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """The relay publishes pending events and stamps them as published."""
    await _seed_two_events(session_factory, make_create_command)
    publisher = CollectingPublisher()
    relay = OutboxRelay(session_factory, publisher)

    published = await relay.dispatch_pending()

    assert published == 2
    assert len(publisher.published) == 2
    async with session_factory() as session:
        rows = (await session.execute(select(OutboxEvent))).scalars().all()
        assert all(row.published_at is not None for row in rows)


async def test_relay_is_idempotent_across_passes(
    session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
) -> None:
    """A second pass publishes nothing because all events are already marked published."""
    await _seed_two_events(session_factory, make_create_command)
    publisher = CollectingPublisher()
    relay = OutboxRelay(session_factory, publisher)

    first = await relay.dispatch_pending()
    second = await relay.dispatch_pending()

    assert first == 2
    assert second == 0
    assert len(publisher.published) == 2
