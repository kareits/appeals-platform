"""Tests for the pure ticket-lifecycle invariants."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from ticket_service.domain.invariants import (
    ClosureState,
    TicketInvariantError,
    check_can_close,
    check_registration_fields,
    resolve_retention_until,
)


def _valid_registration_values() -> dict[str, object]:
    """Build a mapping that satisfies every registration requirement.

    Returns:
        A complete set of required registration field values.
    """
    now = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)
    return {
        "registration_number": "AP-2026-000001",
        "received_at": now,
        "registered_at": now,
        "source_channel_code": "EMAIL",
        "subject": "Restructuring request",
        "description": "Full appeal text",
        "product_code": "MICROLOAN",
        "classifier_code": "RESTRUCTURING",
        "priority_code": "NORMAL",
        "current_status_code": "NEW",
        "current_stage_code": "REGISTRATION",
    }


def test_registration_accepts_complete_values() -> None:
    """A complete set of required fields passes validation."""
    check_registration_fields(_valid_registration_values())


def test_registration_ignores_optional_demographics() -> None:
    """Absent conditional/demographic fields do not block registration (docs/01)."""
    values = _valid_registration_values()
    # No applicant identifier, gender, region, decision, or deadlines are present.
    check_registration_fields(values)


@pytest.mark.parametrize("missing_field", ["subject", "product_code", "current_status_code"])
def test_registration_rejects_missing_required(missing_field: str) -> None:
    """A missing required field is reported by name."""
    values = _valid_registration_values()
    values[missing_field] = None

    with pytest.raises(TicketInvariantError) as excinfo:
        check_registration_fields(values)
    assert missing_field in excinfo.value.missing_fields


def test_registration_rejects_blank_string() -> None:
    """A whitespace-only required field counts as missing."""
    values = _valid_registration_values()
    values["subject"] = "   "

    with pytest.raises(TicketInvariantError):
        check_registration_fields(values)


def _closeable_state() -> ClosureState:
    """Build closure state that satisfies every close prerequisite.

    Returns:
        A fully populated closure state.
    """
    return ClosureState(
        decision_code="REJECTED",
        decision_text="Decision rationale",
        decision_at=datetime(2026, 7, 21, tzinfo=UTC),
        decision_by=uuid.uuid4(),
        response_sent_at=datetime(2026, 7, 22, tzinfo=UTC),
        no_response_reason=None,
        closure_reason_code="RESOLVED",
    )


def test_can_close_when_all_prerequisites_present() -> None:
    """Closure is allowed once every prerequisite is satisfied."""
    check_can_close(_closeable_state())


def test_close_blocked_without_decision() -> None:
    """Closure is blocked when the decision is missing (docs/01)."""
    state = ClosureState(
        decision_code=None,
        decision_text=None,
        decision_at=None,
        decision_by=None,
        response_sent_at=datetime(2026, 7, 22, tzinfo=UTC),
        no_response_reason=None,
        closure_reason_code="RESOLVED",
    )

    with pytest.raises(TicketInvariantError) as excinfo:
        check_can_close(state)
    assert "decision_code" in excinfo.value.missing_fields
    assert "closure_reason_code" not in excinfo.value.missing_fields


def test_close_blocked_without_closure_reason() -> None:
    """Closure is blocked when the closure reason is missing."""
    state = ClosureState(
        decision_code="APPROVED",
        decision_text="Approved",
        decision_at=datetime(2026, 7, 21, tzinfo=UTC),
        decision_by=uuid.uuid4(),
        response_sent_at=datetime(2026, 7, 22, tzinfo=UTC),
        no_response_reason=None,
        closure_reason_code=None,
    )

    with pytest.raises(TicketInvariantError):
        check_can_close(state)


def test_close_allows_justified_absence_of_response() -> None:
    """A recorded reason for the absence of a response substitutes for a response date."""
    state = ClosureState(
        decision_code="REJECTED",
        decision_text="Decision rationale",
        decision_at=datetime(2026, 7, 21, tzinfo=UTC),
        decision_by=uuid.uuid4(),
        response_sent_at=None,
        no_response_reason="Customer withdrew the appeal",
        closure_reason_code="WITHDRAWN",
    )

    check_can_close(state)


def test_close_blocked_without_response_or_reason() -> None:
    """Closure is blocked when neither a response date nor a justification is present."""
    state = ClosureState(
        decision_code="REJECTED",
        decision_text="Decision rationale",
        decision_at=datetime(2026, 7, 21, tzinfo=UTC),
        decision_by=uuid.uuid4(),
        response_sent_at=None,
        no_response_reason=None,
        closure_reason_code="RESOLVED",
    )

    with pytest.raises(TicketInvariantError) as excinfo:
        check_can_close(state)
    assert "response_sent_at|no_response_reason" in excinfo.value.missing_fields


def test_retention_is_five_years_by_default() -> None:
    """Retention defaults to five years after the closure date (docs/01)."""
    closed_at = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)

    assert resolve_retention_until(closed_at) == date(2031, 7, 21)


def test_retention_handles_leap_day_closure() -> None:
    """A Feb 29 closure retains at least the full period (no shortening to Feb 28)."""
    closed_at = datetime(2028, 2, 29, 12, 0, tzinfo=UTC)

    assert resolve_retention_until(closed_at) == date(2033, 3, 1)
