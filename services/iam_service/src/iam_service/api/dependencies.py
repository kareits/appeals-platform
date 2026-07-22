"""FastAPI dependencies for the IAM API.

Provides a request-scoped database session (the unit of work), access to the token issuer, and
bearer-token authorization. Route handlers commit explicitly on success; the session context rolls
back and closes on any error, so a failed request never persists a partial change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mfo_http import ProblemDetail, ProblemDetailError
from sqlalchemy.ext.asyncio import AsyncSession

from iam_service.config import Settings
from iam_service.domain.permissions import Permission
from iam_service.infrastructure.tokens import TokenClaims, TokenError, TokenIssuer

# Declared as a security dependency so the generated OpenAPI advertises bearer authentication on the
# protected operations, matching the committed contract (CR-IAM-MEDIUM-001). ``scheme_name`` and
# ``bearerFormat`` are pinned to the contract's ``bearerAuth`` scheme so the runtime security
# reference is identical, not just present. ``auto_error`` is off so missing/!bearer credentials
# produce our RFC 7807 401 rather than FastAPI's default 403.
_bearer_scheme = HTTPBearer(
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    auto_error=False,
    description="Signed access token issued by POST /api/v1/auth/login.",
)


def build_problem(status: int, title: str, detail: str | None = None) -> ProblemDetailError:
    """Build an RFC 7807 Problem Details error.

    Args:
        status: HTTP status code.
        title: Short problem title.
        detail: Optional occurrence-specific detail.

    Returns:
        The error to raise.
    """
    return ProblemDetailError(ProblemDetail(title=title, status=status, detail=detail))


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


def get_settings_dep(request: Request) -> Settings:
    """Return the settings held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The application settings.
    """
    settings: Settings = request.app.state.settings
    return settings


def get_token_issuer(request: Request) -> TokenIssuer:
    """Return the token issuer held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The shared token issuer.
    """
    issuer: TokenIssuer = request.app.state.token_issuer
    return issuer


def require_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
) -> TokenClaims:
    """Extract and verify the bearer access token, returning its claims.

    Args:
        credentials: The parsed bearer credentials, or ``None`` when absent/not a bearer scheme.
        issuer: The token issuer used to verify the token.

    Returns:
        The validated token claims.

    Raises:
        ProblemDetailError: 401 when the credentials are missing/malformed or the token is invalid.
    """
    if credentials is None or not credentials.credentials.strip():
        raise build_problem(401, "Not authenticated", "a bearer access token is required")
    try:
        return issuer.verify(credentials.credentials.strip())
    except TokenError as exc:
        raise build_problem(401, "Invalid token", str(exc)) from exc


def require_permission(
    permission: Permission,
) -> Callable[[TokenClaims], Coroutine[Any, Any, TokenClaims]]:
    """Build a dependency that requires a specific permission claim.

    Args:
        permission: The permission the subject must hold.

    Returns:
        An async dependency returning the claims when authorized.
    """

    async def _dependency(
        claims: Annotated[TokenClaims, Depends(require_claims)],
    ) -> TokenClaims:
        """Authorize the request against the required permission.

        Args:
            claims: The verified token claims.

        Returns:
            The claims when the required permission is present.

        Raises:
            ProblemDetailError: 403 when the subject lacks the required permission.
        """
        if permission.value not in claims.permissions:
            raise build_problem(
                403, "Forbidden", f"the {permission.value!r} permission is required"
            )
        return claims

    return _dependency
