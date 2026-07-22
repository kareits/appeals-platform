"""Domain event construction for the ticket service.

Builds canonical events (envelope + payload) for the ticket lifecycle. Payloads follow the JSON
Schemas under ``contracts/events/payloads`` and minimize personal data: national identifiers are
masked and update events carry only the names of changed fields (ADR-006, docs/06). Events are
staged through the transactional outbox (see :mod:`ticket_service.infrastructure.outbox`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mfo_observability import get_correlation_id

from ticket_service.infrastructure.ids import uuid7
from ticket_service.infrastructure.masking import mask_identifier
from ticket_service.infrastructure.models import Ticket, TicketApplicant

PRODUCER = "ticket-service"
"""Producer name stamped on every event this service emits."""

AGGREGATE_TICKET = "ticket"
"""Aggregate type for ticket events."""

TICKET_CREATED = "ticket.created.v1"
"""Event type emitted when an appeal is registered."""

TICKET_CLASSIFIED = "ticket.classified.v1"
"""Event type emitted when an appeal is classified."""

TICKET_UPDATED = "ticket.updated.v1"
"""Event type emitted when appeal-card details change."""

TICKET_DECISION_RECORDED = "ticket.decision_recorded.v1"
"""Event type emitted when a decision is recorded."""

TICKET_CLOSED = "ticket.closed.v1"
"""Event type emitted when an appeal is closed."""


@dataclass(frozen=True)
class Event:
    """A fully-formed domain event ready to be staged in the outbox.

    Attributes:
        event_id: Unique event identifier (consumers deduplicate on it).
        event_type: Canonical ``<namespace>.<name>.v<version>`` type.
        event_version: Payload schema version.
        occurred_at: UTC timestamp when the event occurred.
        producer: Producing service name.
        correlation_id: Correlation identifier (canonical UUID string).
        causation_id: Identifier of the causing event/command, or ``None``.
        aggregate_type: Aggregate kind that emitted the event.
        aggregate_id: Identifier of the emitting aggregate.
        payload: Event-specific body.
    """

    event_id: uuid.UUID
    event_type: str
    event_version: int
    occurred_at: datetime
    producer: str
    correlation_id: str
    causation_id: str | None
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]


def _canonical_correlation_id() -> str:
    """Return the current correlation ID as a canonical UUID string.

    The correlation middleware stores a hex UUID; other producers may set a hyphenated one. A fresh
    UUID is generated when no correlation ID is bound, so every event carries a valid one.

    Returns:
        A canonical (hyphenated) UUID string.
    """
    raw = get_correlation_id()
    if raw is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        # A non-UUID correlation value should not break publishing; derive a stable UUID from it.
        return str(uuid.uuid5(uuid.NAMESPACE_OID, raw))


def _version_of(event_type: str) -> int:
    """Extract the integer payload version from a canonical event type.

    Args:
        event_type: A ``<namespace>.<name>.vN`` event type.

    Returns:
        The integer ``N`` from the version suffix.
    """
    return int(event_type.rsplit(".v", 1)[1])


def _new_event(event_type: str, aggregate_id: uuid.UUID, payload: dict[str, Any]) -> Event:
    """Assemble an :class:`Event` with generated identity and timestamp.

    Args:
        event_type: Canonical event type.
        aggregate_id: Identifier of the emitting ticket.
        payload: The event payload.

    Returns:
        The assembled event.
    """
    return Event(
        event_id=uuid7(),
        event_type=event_type,
        event_version=_version_of(event_type),
        occurred_at=datetime.now(UTC),
        producer=PRODUCER,
        correlation_id=_canonical_correlation_id(),
        causation_id=None,
        aggregate_type=AGGREGATE_TICKET,
        aggregate_id=aggregate_id,
        payload=payload,
    )


def _applicant_summary(applicant: TicketApplicant | None) -> dict[str, Any]:
    """Build the privacy-minimized applicant block for the created event.

    Args:
        applicant: The consumer party, or ``None`` if absent.

    Returns:
        A payload fragment with a masked identifier only (never the full value).
    """
    if applicant is None:
        return {
            "applicantType": "CONSUMER",
            "identifierType": None,
            "identifierMasked": None,
            "regionCode": None,
        }
    identifier_type = applicant.identifier_type.value if applicant.identifier_type else None
    return {
        "applicantType": applicant.applicant_type.value,
        "identifierType": identifier_type,
        "identifierMasked": mask_identifier(applicant.identifier_value),
        "regionCode": applicant.region_code,
    }


def ticket_created_event(
    ticket: Ticket, consumer: TicketApplicant | None, has_representative: bool
) -> Event:
    """Build the ``ticket.created.v1`` event for a newly registered appeal.

    Args:
        ticket: The persisted ticket.
        consumer: The consumer party attached to the ticket, if any.
        has_representative: Whether a representative party is attached.

    Returns:
        The created event, with the applicant's identifier masked.
    """
    payload: dict[str, Any] = {
        "ticketId": str(ticket.id),
        "registrationNumber": ticket.registration_number,
        "receivedAt": _iso(ticket.received_at),
        "registeredAt": _iso(ticket.registered_at),
        "sourceChannelCode": ticket.source_channel_code,
        "productCode": ticket.product_code,
        "classifierCode": ticket.classifier_code,
        "priorityCode": ticket.priority_code,
        "currentStatusCode": ticket.current_status_code,
        "currentStageCode": ticket.current_stage_code,
        "subject": ticket.subject,
        "contractNumber": ticket.contract_number,
        "applicant": _applicant_summary(consumer),
        "hasRepresentative": has_representative,
    }
    return _new_event(TICKET_CREATED, ticket.id, payload)


def ticket_classified_event(ticket: Ticket) -> Event:
    """Build the ``ticket.classified.v1`` event.

    Args:
        ticket: The reclassified ticket.

    Returns:
        The classified event.
    """
    payload = {
        "ticketId": str(ticket.id),
        "productCode": ticket.product_code,
        "classifierCode": ticket.classifier_code,
        "priorityCode": ticket.priority_code,
    }
    return _new_event(TICKET_CLASSIFIED, ticket.id, payload)


def ticket_updated_event(ticket_id: uuid.UUID, changed_fields: list[str]) -> Event:
    """Build the ``ticket.updated.v1`` event.

    Args:
        ticket_id: The updated ticket's identifier.
        changed_fields: Names of the card fields that changed.

    Returns:
        The updated event carrying only the changed-field names (no values, to avoid leaking PII).
    """
    payload = {"ticketId": str(ticket_id), "changedFields": changed_fields}
    return _new_event(TICKET_UPDATED, ticket_id, payload)


def ticket_decision_recorded_event(ticket: Ticket) -> Event:
    """Build the ``ticket.decision_recorded.v1`` event.

    Args:
        ticket: The ticket whose decision was recorded (decision fields populated).

    Returns:
        The decision-recorded event.
    """
    payload = {
        "ticketId": str(ticket.id),
        "decisionCode": ticket.decision_code,
        "decisionAt": _iso(ticket.decision_at) if ticket.decision_at else None,
        "decisionBy": str(ticket.decision_by) if ticket.decision_by else None,
    }
    return _new_event(TICKET_DECISION_RECORDED, ticket.id, payload)


def ticket_closed_event(ticket: Ticket) -> Event:
    """Build the ``ticket.closed.v1`` event.

    Args:
        ticket: The closed ticket (closure and retention fields populated).

    Returns:
        The closed event.
    """
    payload = {
        "ticketId": str(ticket.id),
        "closureReasonCode": ticket.closure_reason_code,
        "closedAt": _iso(ticket.closed_at) if ticket.closed_at else None,
        "retentionUntil": ticket.retention_until.isoformat() if ticket.retention_until else None,
    }
    return _new_event(TICKET_CLOSED, ticket.id, payload)


def _iso(value: datetime) -> str:
    """Render a datetime as an ISO-8601 string with a ``Z`` UTC suffix.

    Args:
        value: The timestamp (assumed timezone-aware, UTC in storage).

    Returns:
        The ISO-8601 representation.
    """
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
