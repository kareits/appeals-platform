"""Health-check primitives shared across services.

Defines a health-check protocol, a per-check result, and an aggregate runner that produces an
overall status. Services compose their own readiness checks (for example, database connectivity)
on top of these primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class HealthStatus(StrEnum):
    """Overall or per-check health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@runtime_checkable
class HealthCheck(Protocol):
    """A named asynchronous health check.

    Implementations return ``True`` when the checked dependency is healthy.
    """

    name: str

    async def __call__(self) -> bool:
        """Execute the check.

        Returns:
            ``True`` if the dependency is healthy, ``False`` otherwise.
        """
        ...


@dataclass(frozen=True)
class HealthReport:
    """Aggregate result of running a set of health checks.

    Attributes:
        status: The overall status; unhealthy if any check failed.
        checks: A mapping of check name to its individual status.
    """

    status: HealthStatus
    checks: dict[str, HealthStatus] = field(default_factory=dict)


async def run_health_checks(checks: list[HealthCheck]) -> HealthReport:
    """Run health checks and aggregate their results.

    A check that raises an exception is treated as unhealthy rather than propagating the error, so
    a readiness endpoint always returns a structured report.

    Args:
        checks: The health checks to execute.

    Returns:
        A :class:`HealthReport` whose overall status is healthy only if every check passed.
    """
    results: dict[str, HealthStatus] = {}
    overall = HealthStatus.HEALTHY
    for check in checks:
        try:
            passed = await check()
        except Exception:  # noqa: BLE001 -- a failing dependency must not break the report.
            passed = False
        status = HealthStatus.HEALTHY if passed else HealthStatus.UNHEALTHY
        results[check.name] = status
        if status is HealthStatus.UNHEALTHY:
            overall = HealthStatus.UNHEALTHY
    return HealthReport(status=overall, checks=results)
