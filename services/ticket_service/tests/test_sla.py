"""Tests for SLA deadline computation, retention, and business-timezone handling."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ticket_service.domain.invariants import resolve_retention_until
from ticket_service.domain.sla import DEFAULT_SLA_POLICY, compute_due_dates
from ticket_service.domain.timezone import resolve_timezone


def test_compute_due_dates_uses_policy() -> None:
    """Deadlines are the received time plus the policy resolution hours and legal-term days."""
    received = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)

    due = compute_due_dates(received)

    assert due.internal_due_at == received + timedelta(hours=DEFAULT_SLA_POLICY.resolution_hours)
    assert due.legal_due_at == received + timedelta(days=DEFAULT_SLA_POLICY.legal_term_days)


def test_retention_uses_business_timezone_at_day_boundary() -> None:
    """A late-evening UTC closure counts against the Almaty (UTC+5) day, not the UTC day."""
    # 2026-07-21T20:00Z is 2026-07-22T01:00 in Almaty, so retention starts from the 22nd.
    closed_at = datetime(2026, 7, 21, 20, 0, tzinfo=UTC)

    assert resolve_retention_until(closed_at) == date(2031, 7, 22)


def test_retention_default_five_years() -> None:
    """Retention is five years after the business-timezone closure date."""
    closed_at = datetime(2026, 7, 22, 6, 0, tzinfo=UTC)  # 11:00 Almaty, same date

    assert resolve_retention_until(closed_at) == date(2031, 7, 22)


def test_resolve_timezone_is_utc_plus_five() -> None:
    """The default platform timezone is Kazakhstan time (UTC+5)."""
    tz = resolve_timezone()
    offset = datetime(2026, 7, 22, 12, 0, tzinfo=tz).utcoffset()

    assert offset == timedelta(hours=5)
