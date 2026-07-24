"""FastAPI dependencies for the BFF API.

Provides access to the downstream HTTP clients and the gateway's authorization primitives: a
dependency that resolves the caller's auth context via the IAM service and a factory that enforces a
required permission claim. Bearer authentication is declared as a security dependency so the
generated OpenAPI advertises it on protected operations, matching the committed contract.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mfo_http import PlatformHttpClient, ProblemDetail, ProblemDetailError

from bff_service.application.auth_context import AuthContext, resolve_auth_context
from bff_service.application.errors import (
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from bff_service.config import Settings

# ``scheme_name``/``bearerFormat`` are pinned to the contract's ``bearerAuth`` scheme so the runtime
# security reference is identical, not just present. ``auto_error`` is off so missing/non-bearer
# credentials produce our RFC 7807 401 rather than FastAPI's default 403.
_bearer_scheme = HTTPBearer(
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    auto_error=False,
    description="Signed access token issued by POST /api/v1/auth/login.",
)


@dataclass(frozen=True)
class AuthenticatedCaller:
    """The authenticated caller: the resolved context plus the token to forward downstream.

    Attributes:
        context: The caller's resolved authorization context.
        token: The caller's bearer access token, forwarded to downstream services.
    """

    context: AuthContext
    token: str


def build_problem(
    status: int,
    title: str,
    detail: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    www_authenticate: bool = False,
) -> ProblemDetailError:
    """Build an RFC 7807 Problem Details error, optionally with protocol headers.

    Args:
        status: HTTP status code.
        title: Short problem title.
        detail: Optional occurrence-specific detail.
        headers: Optional response headers to attach.
        www_authenticate: When true, attach a ``WWW-Authenticate: Bearer`` challenge (LOW-001).

    Returns:
        The error to raise.
    """
    resolved = dict(headers) if headers else {}
    if www_authenticate:
        resolved.setdefault("WWW-Authenticate", "Bearer")
    return ProblemDetailError(
        ProblemDetail(title=title, status=status, detail=detail), resolved or None
    )


def get_settings_dep(request: Request) -> Settings:
    """Return the settings held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The application settings.
    """
    settings: Settings = request.app.state.settings
    return settings


def get_iam_client(request: Request) -> PlatformHttpClient:
    """Return the IAM HTTP client held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The client bound to the IAM service base URL.
    """
    client: PlatformHttpClient = request.app.state.iam_client
    return client


def get_ticket_client(request: Request) -> PlatformHttpClient:
    """Return the Ticket Service HTTP client held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The client bound to the Ticket Service base URL.
    """
    client: PlatformHttpClient = request.app.state.ticket_client
    return client


async def require_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    iam_client: Annotated[PlatformHttpClient, Depends(get_iam_client)],
) -> AuthenticatedCaller:
    """Resolve the caller's auth context from the presented bearer token.

    Args:
        credentials: The parsed bearer credentials, or ``None`` when absent/not a bearer scheme.
        iam_client: The IAM HTTP client used to resolve the context.

    Returns:
        The authenticated caller (context plus forwardable token).

    Raises:
        ProblemDetailError: 401 when credentials are missing/rejected; 503 when IAM is unavailable.
    """
    if credentials is None or not credentials.credentials.strip():
        raise build_problem(
            401, "Not authenticated", "a bearer access token is required", www_authenticate=True
        )
    token = credentials.credentials.strip()
    try:
        context = await resolve_auth_context(iam_client, token)
    except UpstreamAuthError as exc:
        raise build_problem(401, "Invalid token", str(exc), www_authenticate=True) from exc
    except UpstreamProtocolError as exc:
        raise build_problem(
            502, "Bad gateway", "the identity service returned a bad response"
        ) from exc
    except UpstreamUnavailableError as exc:
        raise build_problem(503, "Identity service unavailable", str(exc)) from exc
    return AuthenticatedCaller(context=context, token=token)


def require_permission(
    permission: str,
) -> Callable[[AuthenticatedCaller], Coroutine[Any, Any, AuthenticatedCaller]]:
    """Build a dependency that requires a specific permission claim.

    Enforcing at the gateway means an under-privileged caller (for example, first-line read-only) is
    rejected before any downstream call is made.

    Args:
        permission: The permission claim string the caller must hold (``resource:action``).

    Returns:
        An async dependency returning the authenticated caller when authorized.
    """

    async def _dependency(
        caller: Annotated[AuthenticatedCaller, Depends(require_auth_context)],
    ) -> AuthenticatedCaller:
        """Authorize the request against the required permission.

        Args:
            caller: The authenticated caller.

        Returns:
            The caller when the required permission is present.

        Raises:
            ProblemDetailError: 403 when the caller lacks the required permission.
        """
        if not caller.context.has_permission(permission):
            raise build_problem(403, "Forbidden", f"the {permission!r} permission is required")
        return caller

    return _dependency
