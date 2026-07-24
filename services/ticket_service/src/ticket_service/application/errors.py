"""Application-layer errors for ticket use cases.

These are transport-agnostic; the API layer maps them to RFC 7807 Problem Details responses.
"""

from __future__ import annotations


class AuthenticationError(Exception):
    """Raised when a request carries no valid authenticated caller (mapped to 401)."""


class AuthorizationError(Exception):
    """Raised when an authenticated caller lacks the required permission or data scope (403)."""


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different request payload (mapped to 409).

    Idempotency keys are scoped to the authenticated caller; a mismatched payload for the same
    caller/key is a conflict rather than a silent replay of the original result.
    """


class LegacyIdempotencyError(Exception):
    """Raised when a request replays a pre-upgrade (legacy) idempotency key (mapped to 409).

    Rows registered before idempotency keys were scoped to the caller stored a raw, unscoped key
    with no request fingerprint and no trusted subject. Their original actor and canonical request
    cannot be reconstructed, so a retry using that raw key is refused with a non-disclosing conflict
    (reconciliation required) instead of creating a duplicate regulatory record (R3-HIGH-001).
    """


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
