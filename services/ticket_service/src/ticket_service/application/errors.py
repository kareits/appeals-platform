"""Application-layer errors for ticket use cases.

These are transport-agnostic; the API layer maps them to RFC 7807 Problem Details responses.
"""

from __future__ import annotations


class TicketNotFoundError(Exception):
    """Raised when a referenced ticket does not exist."""


class UnknownReferenceCodeError(Exception):
    """Raised when a request uses a dictionary code that is unknown or inactive.

    Attributes:
        invalid: The offending ``(dictionary_type, code)`` pairs.
    """

    def __init__(self, invalid: list[tuple[str, str]]) -> None:
        """Initialize the error.

        Args:
            invalid: The ``(dictionary_type, code)`` pairs that failed validation.
        """
        detail = ", ".join(f"{dictionary_type}={code!r}" for dictionary_type, code in invalid)
        super().__init__(f"unknown or inactive reference code(s): {detail}")
        self.invalid = invalid


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
