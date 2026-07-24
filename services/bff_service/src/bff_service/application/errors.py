"""Application-level errors for the BFF gateway.

These translate downstream failure modes into gateway outcomes: an upstream authentication rejection
becomes a 401, an unreachable upstream becomes a 503, and a malformed/unexpected upstream success
becomes a 502. The API layer maps them to RFC 7807 Problem Details responses.
"""

from __future__ import annotations


class UpstreamAuthError(Exception):
    """Raised when a downstream service rejects the caller's credentials.

    The IAM service returned 401 for the presented token, so the caller is unauthenticated at the
    gateway as well.
    """


class UpstreamUnavailableError(Exception):
    """Raised when a downstream service is unreachable (transport failure or non-response).

    Attributes:
        service: The downstream service name, for diagnostics (for example, ``"iam"``).
    """

    def __init__(self, service: str, detail: str | None = None) -> None:
        """Initialize the error.

        Args:
            service: The downstream service name.
            detail: Optional occurrence-specific detail.
        """
        super().__init__(detail or f"{service} is unavailable")
        self.service = service


class UpstreamProtocolError(Exception):
    """Raised when a downstream success response is malformed or of an unexpected shape.

    A malformed identity response (wrong media type, invalid JSON, or an invalid claim structure)
    must not escape as a 500 or be trusted; the gateway maps it to a safe 502 (CR-BFF-RR-HIGH-003).

    Attributes:
        service: The downstream service name, for diagnostics.
    """

    def __init__(self, service: str, detail: str | None = None) -> None:
        """Initialize the error.

        Args:
            service: The downstream service name.
            detail: Optional occurrence-specific detail.
        """
        super().__init__(detail or f"{service} returned a malformed response")
        self.service = service
