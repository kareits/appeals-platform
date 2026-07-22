"""Audit-log writing.

Records the mutations the ticket service owns (docs/06). Entries are staged in the caller's
transaction (never committed here) and must not contain unmasked personal data; ``details`` carries
only non-sensitive context. The correlation ID is captured automatically to tie an action to its
request.
"""

from __future__ import annotations

import uuid
from typing import Any

from mfo_observability import get_correlation_id
from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.infrastructure.models import AuditLog

ENTITY_TICKET = "ticket"
"""Entity type recorded for ticket actions."""

# Audited action codes for the mutations this service owns.
ACTION_REGISTERED = "ticket.registered"
ACTION_UPDATED = "ticket.updated"
ACTION_CLASSIFIED = "ticket.classified"
ACTION_DECISION_RECORDED = "ticket.decision_recorded"
ACTION_CLOSED = "ticket.closed"
ACTION_LEGAL_HOLD_SET = "ticket.legal_hold_set"


class AuditRepository:
    """Stages audit-log entries into the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active session whose transaction will own the entry.
        """
        self._session = session

    def record(
        self,
        *,
        entity_id: uuid.UUID,
        action: str,
        actor_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
        entity_type: str = ENTITY_TICKET,
    ) -> None:
        """Stage an audit entry for a mutation.

        Args:
            entity_id: Identifier of the entity acted upon.
            action: The audited action code.
            actor_id: Identifier of the actor, if known.
            details: Non-sensitive structured context (must not contain unmasked personal data).
            entity_type: The entity kind (defaults to ``ticket``).
        """
        self._session.add(
            AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_id=actor_id,
                correlation_id=get_correlation_id(),
                details=details,
            )
        )
