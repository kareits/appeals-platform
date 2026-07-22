"""Transactional outbox: staging and relaying domain events.

Events are staged (:class:`OutboxRepository`) in the same transaction as the state change that
produced them, guaranteeing an event is persisted if and only if its change commits (ADR-0004). A
relay (:class:`OutboxRelay`) later reads unpublished rows, publishes their envelopes to the broker
through an :class:`EventPublisher`, and stamps ``published_at``. Delivery is at-least-once;
consumers deduplicate on ``eventId``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ticket_service.application.events import Event
from ticket_service.infrastructure.models import OutboxEvent

_logger = logging.getLogger(__name__)


def _iso(value: datetime) -> str:
    """Render a datetime as ISO-8601 with a ``Z`` UTC suffix.

    Args:
        value: The timestamp to format.

    Returns:
        The ISO-8601 representation.
    """
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def envelope_from_row(row: OutboxEvent) -> dict[str, Any]:
    """Reconstruct the canonical event envelope from an outbox row.

    Args:
        row: The staged outbox event.

    Returns:
        The envelope dictionary as published on the broker (matches ``event-envelope.v1.json``).
    """
    return {
        "eventId": str(row.event_id),
        "eventType": row.event_type,
        "eventVersion": row.event_version,
        "occurredAt": _iso(row.occurred_at),
        "producer": row.producer,
        "correlationId": row.correlation_id,
        "causationId": row.causation_id,
        "payload": row.payload,
    }


class OutboxRepository:
    """Stages domain events into the outbox within the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active session whose transaction will own the staged rows.
        """
        self._session = session

    async def enqueue(self, event: Event) -> None:
        """Stage an event for later publication.

        The row is added to the current session but not committed here; it commits with the
        surrounding unit of work.

        Args:
            event: The event to stage.
        """
        self._session.add(
            OutboxEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                event_version=event.event_version,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                occurred_at=event.occurred_at,
                producer=event.producer,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                payload=event.payload,
            )
        )


class EventPublisher(Protocol):
    """Publishes an event envelope to the message broker."""

    async def publish(self, envelope: dict[str, Any]) -> None:
        """Publish a single event envelope.

        Args:
            envelope: The canonical event envelope to publish.
        """
        ...


class OutboxRelay:
    """Publishes pending outbox events and marks them as published.

    A single relay instance is safe to poll on an interval; each pass claims a batch of unpublished
    rows, publishes them, and stamps ``published_at`` so they are not re-sent.
    """

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], publisher: EventPublisher
    ) -> None:
        """Initialize the relay.

        Args:
            session_factory: Factory used to open the relay's own sessions.
            publisher: The publisher events are sent through.
        """
        self._session_factory = session_factory
        self._publisher = publisher

    async def dispatch_pending(self, batch_size: int = 100) -> int:
        """Publish one batch of pending events, oldest first.

        Each event is published, then marked published in the same session. A publish failure
        aborts the pass without marking the failed (or remaining) events, so they are retried on the
        next pass (at-least-once).

        Args:
            batch_size: Maximum number of events to publish in this pass.

        Returns:
            The number of events successfully published.
        """
        published = 0
        async with self._session_factory() as session:
            # Claim a disjoint batch across concurrent relays: FOR UPDATE SKIP LOCKED skips rows
            # another instance is already publishing (CR-MEDIUM-003). On SQLite the clause is a
            # no-op and single-writer semantics apply. Consumers still deduplicate on eventId
            # because publish/commit remains inherently at-least-once.
            rows = (
                (
                    await session.execute(
                        select(OutboxEvent)
                        .where(OutboxEvent.published_at.is_(None))
                        .order_by(OutboxEvent.created_at)
                        .limit(batch_size)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                await self._publisher.publish(envelope_from_row(row))
                row.published_at = datetime.now(UTC)
                published += 1
            await session.commit()
        return published


class NullEventPublisher:
    """A publisher that discards events; used when no broker is configured (local/tests)."""

    async def publish(self, envelope: dict[str, Any]) -> None:
        """Log and drop the envelope.

        Args:
            envelope: The event envelope that would have been published.
        """
        _logger.debug("event dropped by NullEventPublisher: %s", envelope.get("eventType"))


class RabbitMqEventPublisher:
    """Publishes events to a RabbitMQ topic exchange via aio-pika.

    The routing key is the canonical ``eventType`` so consumers bind by namespace/name. The
    connection is opened lazily on first publish and reused.
    """

    def __init__(self, url: str, exchange: str) -> None:
        """Initialize the publisher.

        Args:
            url: The AMQP connection URL.
            exchange: The topic exchange to publish to.
        """
        self._url = url
        self._exchange_name = exchange
        self._connection: Any = None
        self._exchange: Any = None

    async def _ensure_exchange(self) -> Any:
        """Open the connection and declare the exchange on first use.

        Returns:
            The declared topic exchange.
        """
        # Imported lazily so the broker dependency is only needed when publishing is enabled.
        import aio_pika

        if self._exchange is None:
            self._connection = await aio_pika.connect_robust(self._url)
            channel = await self._connection.channel()
            self._exchange = await channel.declare_exchange(
                self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
            )
        return self._exchange

    async def publish(self, envelope: dict[str, Any]) -> None:
        """Publish an event envelope as a persistent JSON message.

        Args:
            envelope: The canonical event envelope to publish.
        """
        import json

        import aio_pika

        exchange = await self._ensure_exchange()
        message = aio_pika.Message(
            body=json.dumps(envelope).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=envelope["eventId"],
            correlation_id=envelope["correlationId"],
        )
        await exchange.publish(message, routing_key=envelope["eventType"])

    async def close(self) -> None:
        """Close the broker connection if it was opened."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._exchange = None
