"""HTTP routes for dev/local authentication.

Handlers are thin: they enforce dev-auth availability, invoke the authentication use case, commit
the audit write, and map the result (and failures) to responses. No business logic lives here
(root ``CLAUDE.md``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from iam_service.api.dependencies import (
    build_problem,
    get_session,
    get_settings_dep,
    get_token_issuer,
    require_claims,
)
from iam_service.api.schemas import LoginRequest, SubjectResponse, TokenResponse
from iam_service.application import use_cases
from iam_service.application.errors import AuthenticationError
from iam_service.config import Settings
from iam_service.domain.roles import Role
from iam_service.infrastructure.tokens import TokenClaims, TokenIssuer

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _roles_from_claims(role_names: tuple[str, ...]) -> list[Role]:
    """Map role-name claims to :class:`Role`, failing closed on an unknown value.

    A correctly signed token that carries a role this service does not recognize must be rejected as
    unauthenticated rather than raise a 500 (CR-IAM-MEDIUM-005).

    Args:
        role_names: The role names carried by the token.

    Returns:
        The corresponding roles.

    Raises:
        ProblemDetailError: 401 when any role name is not a known role.
    """
    try:
        return [Role(name) for name in role_names]
    except ValueError as exc:
        raise build_problem(401, "Invalid token", "token carries an unknown role") from exc


@router.post("/login", response_model=TokenResponse, operation_id="devLogin")
async def dev_login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
) -> TokenResponse:
    """Authenticate with the dev/local scheme and return a signed access token.

    Args:
        body: The login credentials.
        session: The unit-of-work session (owns the authentication audit write).
        settings: Application settings (used to gate dev-auth availability).
        issuer: The token issuer.

    Returns:
        The access token and the subject's resolved claims.

    Raises:
        ProblemDetailError: 403 when dev authentication is unavailable; 401 on invalid credentials.
    """
    if not settings.dev_auth_available:
        raise build_problem(
            403,
            "Dev authentication disabled",
            "dev/local login is not available in this environment",
        )
    try:
        result = await use_cases.authenticate_dev(
            session, username=body.username, password=body.password, issuer=issuer
        )
    except AuthenticationError as exc:
        raise build_problem(401, "Authentication failed", str(exc)) from exc
    await session.commit()
    return TokenResponse(
        access_token=result.token,
        token_type="Bearer",
        expires_in=result.expires_in,
        subject=result.user.id,
        username=result.user.username,
        roles=_roles_from_claims(result.roles),
        permissions=list(result.permissions),
    )


@router.get("/me", response_model=SubjectResponse, operation_id="getCurrentSubject")
async def get_current_subject(
    claims: Annotated[TokenClaims, Depends(require_claims)],
) -> SubjectResponse:
    """Return the current subject's claims decoded from the bearer token.

    Args:
        claims: The verified token claims.

    Returns:
        The subject, username, roles, and permissions carried by the token.
    """
    return SubjectResponse(
        subject=claims.subject,
        username=claims.username,
        roles=_roles_from_claims(claims.roles),
        permissions=list(claims.permissions),
    )
