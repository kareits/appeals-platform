"""Correlation-ID propagation via a context variable.

The correlation ID ties together logs, HTTP calls, and events belonging to a single logical
request. It is stored in a :class:`contextvars.ContextVar` so it is isolated per async task.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

CORRELATION_ID_HEADER = "X-Correlation-ID"
"""Canonical HTTP header name carrying the correlation ID."""

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def generate_correlation_id() -> str:
    """Generate a new random correlation ID.

    Returns:
        A hex UUID4 string suitable for use as a correlation ID.
    """
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """Return the correlation ID bound to the current context, if any.

    Returns:
        The current correlation ID, or ``None`` when none has been set.
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    """Bind a correlation ID to the current context.

    Args:
        correlation_id: The identifier to associate with the current task.
    """
    _correlation_id.set(correlation_id)
