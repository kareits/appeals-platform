"""Pure domain invariants for the ticket lifecycle.

These functions encode regulatory rules independently of persistence so they can be unit-tested in
isolation and reused by the use cases introduced in later subtasks (01B/01C). They raise
:class:`TicketInvariantError` rather than returning flags, so a violated invariant cannot be
silently ignored by a caller.

Scope note (TASK_01A): the model and these rule definitions land here; the use cases that invoke
them on state transitions (``RecordDecision``, close) are implemented in TASK_01C.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime


class TicketInvariantError(ValueError):
    """Raised when a ticket would violate a regulatory invariant.

    Attributes:
        missing_fields: The names of fields whose absence caused the violation, when applicable.
    """

    def __init__(self, message: str, missing_fields: tuple[str, ...] = ()) -> None:
        """Initialize the error.

        Args:
            message: Human-readable, developer-facing description of the violation.
            missing_fields: Names of the fields that were required but absent.
        """
        super().__init__(message)
        self.missing_fields = missing_fields


# Fields required to register any written appeal. Conditional/demographic fields are intentionally
# excluded: per docs/01 they are nullable and must not block registration.
REQUIRED_AT_REGISTRATION: tuple[str, ...] = (
    "registration_number",
    "received_at",
    "registered_at",
    "source_channel_code",
    "subject",
    "description",
    "product_code",
    "classifier_code",
    "priority_code",
    "current_status_code",
    "current_stage_code",
)


def check_registration_fields(values: Mapping[str, object]) -> None:
    """Verify that all fields required to register an appeal are present and non-empty.

    Args:
        values: A mapping of field name to value for the ticket being registered.

    Raises:
        TicketInvariantError: If any required field is missing, ``None``, or an empty/blank string.
    """
    missing = tuple(name for name in REQUIRED_AT_REGISTRATION if _is_absent(values.get(name)))
    if missing:
        raise TicketInvariantError(
            f"missing required registration fields: {', '.join(missing)}",
            missing_fields=missing,
        )


@dataclass(frozen=True)
class ClosureState:
    """The subset of ticket state relevant to the close invariant.

    Attributes:
        decision_code: Code of the recorded decision, if any.
        decision_text: Full text of the decision, if any.
        decision_at: Timestamp the decision was made, if any.
        decision_by: Identifier of the responsible employee, if any.
        response_sent_at: Timestamp the response was sent to the customer, if any.
        no_response_reason: Justification for the absence of a response, if any.
        closure_reason_code: Code explaining why the ticket is being closed, if any.
    """

    decision_code: str | None
    decision_text: str | None
    decision_at: datetime | None
    decision_by: object | None
    response_sent_at: datetime | None
    no_response_reason: str | None
    closure_reason_code: str | None


def check_can_close(state: ClosureState) -> None:
    """Verify a ticket satisfies every prerequisite for closure.

    Closure is blocked unless a decision (code and text), the responsible employee, the decision
    date, either a response date or a justified absence of response, and a closure reason are all
    present (docs/01 "Закрытие"). A response by email never closes a ticket on its own — closure is
    an explicit, validated action (docs/01, ADR-006).

    Args:
        state: The closure-relevant ticket state.

    Raises:
        TicketInvariantError: If any closure prerequisite is unmet.
    """
    missing: list[str] = []
    if _is_absent(state.decision_code):
        missing.append("decision_code")
    if _is_absent(state.decision_text):
        missing.append("decision_text")
    if _is_absent(state.decision_at):
        missing.append("decision_at")
    if _is_absent(state.decision_by):
        missing.append("decision_by")
    if _is_absent(state.closure_reason_code):
        missing.append("closure_reason_code")
    # A response date OR a recorded reason for its absence is required, but not both.
    if _is_absent(state.response_sent_at) and _is_absent(state.no_response_reason):
        missing.append("response_sent_at|no_response_reason")

    if missing:
        raise TicketInvariantError(
            f"cannot close ticket, missing: {', '.join(missing)}",
            missing_fields=tuple(missing),
        )


def resolve_retention_until(closed_at: datetime, retention_years: int = 5) -> date:
    """Compute the regulatory retention date for a closed ticket.

    Appeals are retained for at least five years after closure (docs/01 "Хранение"). The exact
    calendar policy (KZ business calendar) is refined later (Q-C1); here retention is computed as a
    whole-year offset from the closure date.

    Args:
        closed_at: The timestamp the ticket was closed.
        retention_years: The minimum retention period in years (defaults to the regulatory five).

    Returns:
        The earliest date on which the ticket becomes eligible for purge.
    """
    closed_date = closed_at.date()
    target_year = closed_date.year + retention_years
    try:
        return closed_date.replace(year=target_year)
    except ValueError:
        # A Feb 29 closure has no counterpart in a non-leap target year; retaining until Mar 1
        # keeps the full period rather than shortening it to Feb 28.
        return date(target_year, 3, 1)


def _is_absent(value: object) -> bool:
    """Return whether a value counts as missing for invariant purposes.

    Args:
        value: The value to test.

    Returns:
        ``True`` if the value is ``None`` or a string that is empty or only whitespace.
    """
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""
