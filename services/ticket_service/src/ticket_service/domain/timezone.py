"""Platform business-timezone helpers.

Timestamps are always **stored in UTC** (ADR-003). Business *dates* and working-hours math — the
retention date and, later, SLA working-hour calendars — are computed in the platform business
timezone, Kazakhstan (Astana/Almaty), which is UTC+5 with no daylight saving. The zone name is
configurable via ``PLATFORM_TIMEZONE`` so a deployment can override it without code changes.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo

DEFAULT_PLATFORM_TIMEZONE = "Asia/Almaty"
"""Default IANA business timezone (Kazakhstan, UTC+5)."""


def resolve_timezone(name: str = DEFAULT_PLATFORM_TIMEZONE) -> ZoneInfo:
    """Resolve an IANA timezone name to a ``ZoneInfo``.

    Args:
        name: The IANA timezone name (defaults to Asia/Almaty).

    Returns:
        The resolved timezone.
    """
    return ZoneInfo(name)


def to_business_date(instant: datetime, tz: tzinfo | None = None) -> date:
    """Convert a UTC-stored instant to the calendar date in the business timezone.

    Args:
        instant: A timezone-aware instant (UTC in storage).
        tz: The business timezone; defaults to Asia/Almaty.

    Returns:
        The calendar date as seen in the business timezone.
    """
    zone = tz or resolve_timezone()
    return instant.astimezone(zone).date()
