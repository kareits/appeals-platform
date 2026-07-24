"""Ticket permission claim strings enforced by the ticket service.

The ticket service authorizes on permission *claim strings* (``resource:action``), not on role
names, and defines these values independently of the IAM service (ADR-004 forbids importing IAM
code; ADR-007 forbids a shared permission package). IAM resolves a user's roles to permissions and
stamps them as token claims; the ticket service checks the claim strings here. The values must stay
in sync with the strings IAM issues.
"""

from __future__ import annotations

from enum import StrEnum


class TicketPermission(StrEnum):
    """A ticket permission claim string checked on every mutating or reading route.

    Attributes:
        READ: View appeals (card, search, comments).
        CREATE: Register new appeals.
        UPDATE: Edit mutable card details.
        CLASSIFY: Set or change classification.
        COMMENT: Add comments to an appeal.
        DECIDE: Record a regulatory decision on an appeal.
        CLOSE: Close an appeal.
        LEGAL_HOLD: Place or lift a legal hold.
    """

    READ = "ticket:read"
    CREATE = "ticket:create"
    UPDATE = "ticket:update"
    CLASSIFY = "ticket:classify"
    COMMENT = "ticket:comment"
    DECIDE = "ticket:decide"
    CLOSE = "ticket:close"
    LEGAL_HOLD = "ticket:legal_hold"
