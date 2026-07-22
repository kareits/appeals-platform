"""Audit-log writing for identity actions.

Records the security-relevant identity actions the IAM service owns (docs/06): authentication and
role changes. Entries are staged in the caller's transaction (never committed here) and must not
contain credentials; ``details`` carries only non-sensitive context. The correlation ID is captured
automatically to tie an action to its request.
"""

from __future__ import annotations

import uuid
from typing import Any

from mfo_observability import get_correlation_id
from sqlalchemy.ext.asyncio import AsyncSession

from iam_service.infrastructure.models import AuditLog

ENTITY_USER = "user"
"""Entity type recorded for user actions."""

# Audited action codes for the identity mutations this service owns.
ACTION_AUTHENTICATED = "user.authenticated"
ACTION_USER_CREATED = "user.created"
ACTION_ROLE_ASSIGNED = "user.role_assigned"
ACTION_ROLE_REVOKED = "user.role_revoked"


class AuditRepository:
    """Stages identity audit-log entries into the caller's transaction."""

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
        entity_type: str = ENTITY_USER,
    ) -> None:
        """Stage an audit entry for an identity action.

        Args:
            entity_id: Identifier of the entity acted upon.
            action: The audited action code.
            actor_id: Identifier of the actor, if known.
            details: Non-sensitive structured context (must not contain credentials).
            entity_type: The entity kind (defaults to ``user``).
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
