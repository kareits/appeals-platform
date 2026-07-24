"""Permission claim strings the gateway enforces.

The gateway authorizes on permission *claim strings* (``resource:action``), not on role names, so it
stays decoupled from the IAM role-to-permission matrix (ADR-007): IAM resolves roles to permissions
and stamps them as claims; the gateway only checks whether the required claim string is present. The
values here are defined independently of the IAM service (ADR-004 forbids importing its code); they
must stay in sync with the claim strings IAM issues.
"""

from __future__ import annotations

from enum import StrEnum


class TicketPermission(StrEnum):
    """Ticket permission claim strings checked at the gateway.

    Attributes:
        READ: View appeals (search, workspace).
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
