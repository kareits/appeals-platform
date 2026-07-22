"""Business-calendar abstraction for deadline computation.

Deadlines depend on a business calendar (working hours, holidays). The exact KZ calendar is not yet
confirmed (Q-C1), so a temporary continuous calendar is used: every hour and day counts, with no
weekends or holidays. The :class:`BusinessCalendar` protocol lets a working-hours/holiday-aware
implementation replace it later without changing the SLA computation (ADR-009 / ADR-0005).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol


class BusinessCalendar(Protocol):
    """Computes future instants by adding working hours or calendar days."""

    def add_working_hours(self, start: datetime, hours: int) -> datetime:
        """Return ``start`` advanced by a number of working hours.

        Args:
            start: The starting instant.
            hours: The number of working hours to add.

        Returns:
            The resulting instant.
        """
        ...

    def add_calendar_days(self, start: datetime, days: int) -> datetime:
        """Return ``start`` advanced by a number of calendar days.

        Args:
            start: The starting instant.
            days: The number of calendar days to add.

        Returns:
            The resulting instant.
        """
        ...


class ContinuousCalendar:
    """Temporary calendar treating all time as working time (no weekends or holidays, Q-C1).

    This satisfies the :class:`BusinessCalendar` protocol and is deliberately simple; it is replaced
    by a KZ working-hours/holiday calendar once confirmed.
    """

    def add_working_hours(self, start: datetime, hours: int) -> datetime:
        """Advance by wall-clock hours (every hour is a working hour here).

        Args:
            start: The starting instant.
            hours: The number of hours to add.

        Returns:
            ``start + hours``.
        """
        return start + timedelta(hours=hours)

    def add_calendar_days(self, start: datetime, days: int) -> datetime:
        """Advance by calendar days.

        Args:
            start: The starting instant.
            days: The number of days to add.

        Returns:
            ``start + days``.
        """
        return start + timedelta(days=days)
