"""FastAPI dependencies for the ticket API.

Provides a request-scoped database session (the unit of work), the registration-number allocator,
and the service's independent authentication/authorization primitives: bearer-token verification
into caller claims (401 on failure) and a required-permission gate (403). The ticket service is a
security boundary in its own right — it authenticates and authorizes every request even when reached
directly, without the BFF (CR-BFF-BLOCKER-001).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import tzinfo
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mfo_http import ProblemDetail, ProblemDetailError
from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.domain.timezone import resolve_timezone
from ticket_service.infrastructure.auth_tokens import TicketClaims, TokenError, TokenVerifier
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

# Declared as a security dependency so the generated OpenAPI advertises bearer authentication on the
# protected operations. ``scheme_name``/``bearerFormat`` are pinned to the contract's ``bearerAuth``
# scheme; ``auto_error`` is off so a missing/non-bearer credential yields our RFC 7807 401 with a
# ``WWW-Authenticate`` challenge rather than FastAPI's default 403.
_bearer_scheme = HTTPBearer(
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    auto_error=False,
    description="Signed access token issued by the IAM service.",
)

# Standard authentication challenge attached to every bearer 401 (RFC 6750; CR-BFF-LOW-001).
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def build_problem(
    status: int, title: str, detail: str | None = None, *, headers: dict[str, str] | None = None
) -> ProblemDetailError:
    """Build an RFC 7807 Problem Details error.

    Args:
        status: HTTP status code.
        title: Short problem title.
        detail: Optional occurrence-specific detail.
        headers: Optional response headers (for example, an authentication challenge).

    Returns:
        The error to raise.
    """
    return ProblemDetailError(ProblemDetail(title=title, status=status, detail=detail), headers)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session.

    The session is closed when the request finishes; because handlers commit explicitly, an
    uncommitted session (after an error) is rolled back on close.

    Args:
        request: The incoming request, used to reach the app's session factory.

    Yields:
        An open async session.
    """
    async with request.app.state.session_factory() as session:
        yield session


def get_allocator(request: Request) -> RegistrationNumberAllocator:
    """Return the registration-number allocator held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The shared allocator.
    """
    allocator: RegistrationNumberAllocator = request.app.state.registration_allocator
    return allocator


def get_platform_timezone(request: Request) -> tzinfo:
    """Return the configured platform business timezone.

    Args:
        request: The incoming request.

    Returns:
        The resolved business timezone (default Asia/Almaty) used for business-date computation.
    """
    return resolve_timezone(request.app.state.settings.platform_timezone)


def get_token_verifier(request: Request) -> TokenVerifier:
    """Return the access-token verifier held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The shared token verifier.
    """
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def require_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> TicketClaims:
    """Authenticate the request by verifying its bearer token, returning the caller's claims.

    Args:
        credentials: The parsed bearer credentials, or ``None`` when absent/not a bearer scheme.
        verifier: The token verifier.

    Returns:
        The validated caller claims.

    Raises:
        ProblemDetailError: 401 (with a ``WWW-Authenticate`` challenge) when the credentials are
            missing/malformed or the token is invalid.
    """
    if credentials is None or not credentials.credentials.strip():
        raise build_problem(
            401, "Not authenticated", "a bearer access token is required", headers=_WWW_AUTHENTICATE
        )
    try:
        return verifier.verify(credentials.credentials.strip())
    except TokenError as exc:
        raise build_problem(401, "Invalid token", str(exc), headers=_WWW_AUTHENTICATE) from exc


def require_permission(
    permission: str,
) -> Callable[[TicketClaims], Coroutine[Any, Any, TicketClaims]]:
    """Build a dependency that requires a specific permission claim.

    Args:
        permission: The permission claim string the caller must hold (``resource:action``).

    Returns:
        An async dependency returning the claims when authorized.
    """

    async def _dependency(
        claims: Annotated[TicketClaims, Depends(require_claims)],
    ) -> TicketClaims:
        """Authorize the request against the required permission.

        Args:
            claims: The verified caller claims.

        Returns:
            The claims when the required permission is present.

        Raises:
            ProblemDetailError: 403 when the caller lacks the required permission.
        """
        if not claims.has_permission(permission):
            raise build_problem(403, "Forbidden", f"the {permission!r} permission is required")
        return claims

    return _dependency
