"""Application-layer errors for ticket use cases.

These are transport-agnostic; the API layer maps them to RFC 7807 Problem Details responses.
"""

from __future__ import annotations


class TicketNotFoundError(Exception):
    """Raised when a referenced ticket does not exist."""


class VersionConflictError(Exception):
    """Raised when an optimistic-locking version does not match the stored ticket.

    Attributes:
        expected: The version supplied by the client.
        actual: The version currently stored.
    """

    def __init__(self, expected: int, actual: int) -> None:
        """Initialize the error.

        Args:
            expected: The version the client expected.
            actual: The version currently stored.
        """
        super().__init__(f"version conflict: expected {expected}, actual {actual}")
        self.expected = expected
        self.actual = actual
