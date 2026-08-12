"""FastAPI dependencies for the document API.

Provides a request-scoped database session, the storage backend, and the service's independent
authentication/authorization primitives: bearer-token verification into caller claims (401 on
failure) and a required-permission gate (403). The document service is a security boundary in its
own right — it serves file bytes, so it authenticates and authorizes every request even when reached
directly, without the BFF (CR-BFF-BLOCKER-001 precedent).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mfo_http import ProblemDetail, ProblemDetailError
from sqlalchemy.ext.asyncio import AsyncSession

from document_service.application.commands import Caller
from document_service.domain.scope import AppealScopeChecker
from document_service.domain.storage import FileStorage
from document_service.infrastructure.auth_tokens import DocumentClaims, TokenError, TokenVerifier

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

    The session is closed when the request finishes; because the use cases commit explicitly, an
    uncommitted session (after an error) is rolled back on close.

    Args:
        request: The incoming request, used to reach the app's session factory.

    Yields:
        An open async session.
    """
    async with request.app.state.session_factory() as session:
        yield session


def get_storage(request: Request) -> FileStorage:
    """Return the configured storage backend held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The shared storage backend.
    """
    storage: FileStorage = request.app.state.storage
    return storage


def get_max_upload_bytes(request: Request) -> int:
    """Return the configured maximum upload size.

    Args:
        request: The incoming request.

    Returns:
        The maximum number of bytes accepted for a single upload.
    """
    limit: int = request.app.state.settings.max_upload_bytes
    return limit


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
) -> DocumentClaims:
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


def get_scope_checker(request: Request) -> AppealScopeChecker:
    """Return the appeal-scope decision port held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The shared scope checker.
    """
    checker: AppealScopeChecker = request.app.state.scope_checker
    return checker


def require_caller(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    claims: Annotated[DocumentClaims, Depends(require_claims)],
) -> Caller:
    """Return the authenticated caller, including the raw token for delegated scope decisions.

    The token is forwarded (never a service identity) when another service is asked whether this
    caller may reach an appeal, so the decision is made with the caller's own privileges
    (:mod:`document_service.domain.scope`).

    Args:
        credentials: The parsed bearer credentials; present because ``require_claims`` succeeded.
        claims: The verified caller claims.

    Returns:
        The caller's subject and bearer token.
    """
    # ``require_claims`` has already rejected a missing/blank credential, so this narrows the type
    # rather than performing a second authentication check.
    token = credentials.credentials.strip() if credentials is not None else ""
    return Caller(subject=claims.subject, access_token=token)


def declare_correlation_id(
    # Typed as a plain ``str`` with an empty default rather than ``str | None``: an optional header
    # whose Python type is nullable generates ``anyOf: [string, null]``, which would not match the
    # committed contract's ``type: string`` parameter (CR-DOC-MEDIUM-003). The value is unused.
    x_correlation_id: Annotated[
        str,
        Header(
            alias="X-Correlation-ID",
            description=(
                "Correlation identifier propagated across services; generated when absent."
            ),
        ),
    ] = "",
) -> None:
    """Declare the correlation-ID request header so it appears in the generated OpenAPI document.

    The header is consumed by ``CorrelationIdMiddleware``, which runs before routing and therefore
    contributes nothing to the generated schema. Declaring it as a router-level dependency keeps the
    runtime document honest about a header the service really reads, and keeps it identical to the
    committed contract (CR-DOC-MEDIUM-003).

    Args:
        x_correlation_id: The incoming correlation identifier, if the caller sent one.
    """


def require_permission(
    permission: str,
) -> Callable[[DocumentClaims], Coroutine[Any, Any, DocumentClaims]]:
    """Build a dependency that requires a specific permission claim.

    Args:
        permission: The permission claim string the caller must hold (``resource:action``).

    Returns:
        An async dependency returning the claims when authorized.
    """

    async def _dependency(
        claims: Annotated[DocumentClaims, Depends(require_claims)],
    ) -> DocumentClaims:
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
