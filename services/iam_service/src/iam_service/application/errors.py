"""Application-level errors for the IAM service.

These map to HTTP problem responses at the API boundary (RFC 7807). Keeping them here lets use cases
signal failures without importing FastAPI, preserving the layer boundary.
"""

from __future__ import annotations


class IamError(Exception):
    """Base class for IAM application errors."""


class AuthenticationError(IamError):
    """Raised when credentials are invalid or the account cannot authenticate.

    The message is deliberately non-specific so it does not reveal whether the username exists.
    """


class DevAuthUnavailableError(IamError):
    """Raised when dev/local login is requested but disabled (production or turned off)."""


class UserNotFoundError(IamError):
    """Raised when an operation targets a user that does not exist."""


class UserAlreadyExistsError(IamError):
    """Raised when creating a user whose username is already taken."""


class TeamNotFoundError(IamError):
    """Raised when a referenced team does not exist."""
