"""SLA policy and deadline computation.

The ticket service owns SLA deadlines: it computes ``internal_due_at`` (internal SLA) and
``legal_due_at`` (regulatory term) from a versioned SLA policy and a business calendar; Flowable
sets timers from these values and Notification alerts on them (ADR-009 / ADR-0005). The default
policy uses the temporary parameters from docs/01 (reaction 12h, resolution 24h) and a temporary
15-calendar-day regulatory term (Q-C1); the version is stamped on the ticket for provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ticket_service.domain.business_calendar import BusinessCalendar, ContinuousCalendar


@dataclass(frozen=True)
class SlaPolicy:
    """A versioned set of SLA parameters.

    Attributes:
        version: Stable identifier of this policy version, stamped on tickets for provenance.
        reaction_hours: Target hours to first react to an appeal (not yet stored as a deadline).
        resolution_hours: Internal SLA hours to resolve, used for ``internal_due_at``.
        legal_term_days: Regulatory term in calendar days, used for ``legal_due_at``.
    """

    version: str
    reaction_hours: int
    resolution_hours: int
    legal_term_days: int


# Temporary default derived from docs/01 (reaction 12h, resolution 24h). The 15-calendar-day
# regulatory term is a safe placeholder pending confirmation (Q-C1); the version marks it temporary.
DEFAULT_SLA_POLICY = SlaPolicy(
    version="v1-temp",
    reaction_hours=12,
    resolution_hours=24,
    legal_term_days=15,
)


@dataclass(frozen=True)
class DueDates:
    """Computed appeal deadlines.

    Attributes:
        internal_due_at: The internal SLA deadline.
        legal_due_at: The regulatory deadline.
    """

    internal_due_at: datetime
    legal_due_at: datetime


def compute_due_dates(
    received_at: datetime,
    policy: SlaPolicy = DEFAULT_SLA_POLICY,
    calendar: BusinessCalendar | None = None,
) -> DueDates:
    """Compute internal and legal deadlines for an appeal.

    Args:
        received_at: When the appeal was received (the SLA clock start).
        policy: The SLA policy to apply.
        calendar: The business calendar; defaults to the temporary continuous calendar.

    Returns:
        The internal and legal deadlines.
    """
    active_calendar = calendar or ContinuousCalendar()
    return DueDates(
        internal_due_at=active_calendar.add_working_hours(received_at, policy.resolution_hours),
        legal_due_at=active_calendar.add_calendar_days(received_at, policy.legal_term_days),
    )
