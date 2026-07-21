"""A minimal, dependency-free in-memory counter registry.

This is a lightweight placeholder for real metrics collection. It lets services increment named
counters without pulling in a metrics backend; a production exporter can be introduced later
(EP-7) behind the same interface.
"""

from __future__ import annotations

from threading import Lock


class CounterRegistry:
    """A thread-safe registry of monotonically increasing named counters."""

    def __init__(self) -> None:
        """Initialize an empty counter registry."""
        self._counters: dict[str, int] = {}
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        """Increase a named counter.

        Args:
            name: The counter name.
            amount: The non-negative amount to add. Defaults to 1.

        Raises:
            ValueError: If ``amount`` is negative.
        """
        if amount < 0:
            raise ValueError("Counter increment amount must be non-negative.")
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def value(self, name: str) -> int:
        """Return the current value of a named counter.

        Args:
            name: The counter name.

        Returns:
            The counter value, or 0 if the counter has never been incremented.
        """
        with self._lock:
            return self._counters.get(name, 0)

    def snapshot(self) -> dict[str, int]:
        """Return a copy of all counter values.

        Returns:
            A mapping of counter name to its current value.
        """
        with self._lock:
            return dict(self._counters)
