"""Shared observability primitives for platform services.

Exposes structured logging, correlation-ID propagation, a minimal metrics registry, and
health-check helpers. The scope is bounded by ADR-007 (no domain models, ORM models, business
events, or permission rules).
"""

from mfo_observability.correlation import (
    CORRELATION_ID_HEADER,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from mfo_observability.health import HealthCheck, HealthReport, HealthStatus, run_health_checks
from mfo_observability.logging import configure_logging
from mfo_observability.metrics import CounterRegistry

__all__ = [
    "CORRELATION_ID_HEADER",
    "CounterRegistry",
    "HealthCheck",
    "HealthReport",
    "HealthStatus",
    "configure_logging",
    "generate_correlation_id",
    "get_correlation_id",
    "run_health_checks",
    "set_correlation_id",
]
