"""HTTP routes for user and role administration.

Every route requires the ``iam:manage`` permission. Handlers are thin: they translate requests into
use-case inputs, invoke the application layer, commit the unit of work (writes and their audit
entries together), and map results and domain errors to responses. No business logic lives here
(root ``CLAUDE.md``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from iam_service.api.dependencies import (
    build_problem,
    get_session,
    require_permission,
)
from iam_service.api.schemas import (
    AssignRoleRequest,
    CreateUserRequest,
    UserResponse,
    user_to_response,
)
from iam_service.application import use_cases
from iam_service.application.commands import CreateUserCommand
from iam_service.application.errors import (
    TeamNotFoundError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from iam_service.domain.permissions import Permission
from iam_service.domain.roles import Role
from iam_service.infrastructure.repositories import UserRepository
from iam_service.infrastructure.tokens import TokenClaims

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# Every route in this router requires identity-management permission.
_RequireManage = Annotated[TokenClaims, Depends(require_permission(Permission.IAM_MANAGE))]


@asynccontextmanager
async def _domain_errors() -> AsyncIterator[None]:
    """Translate application/domain errors into RFC 7807 Problem Details.

    Yields:
        Control to the wrapped block; exceptions are converted to Problem Details errors.

    Raises:
        ProblemDetailError: For not-found (404), conflicts (409), and invalid references (422).
    """
    try:
        yield
    except UserNotFoundError as exc:
        raise build_problem(404, "User not found", str(exc)) from exc
    except UserAlreadyExistsError as exc:
        raise build_problem(409, "User already exists", str(exc)) from exc
    except TeamNotFoundError as exc:
        raise build_problem(422, "Invalid team", str(exc)) from exc
    except IntegrityError as exc:
        raise build_problem(409, "Conflict", "the request conflicts with an existing record") from (
            exc
        )


def _actor_id(claims: TokenClaims) -> uuid.UUID:
    """Return the acting administrator's identifier from the token claims.

    Args:
        claims: The verified claims of the caller.

    Returns:
        The administrator's subject identifier.
    """
    return claims.subject


@router.post("", response_model=UserResponse, status_code=201, operation_id="createUser")
async def create_user(
    body: CreateUserRequest,
    claims: _RequireManage,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Create a user with hashed credentials and initial role grants.

    Args:
        body: The creation request.
        claims: The verified claims of the acting administrator.
        session: The unit-of-work session.

    Returns:
        The newly created user.
    """
    command = CreateUserCommand(
        username=body.username,
        full_name=body.full_name,
        password=body.password,
        email=body.email,
        team_id=body.team_id,
        roles=tuple(body.roles),
    )
    async with _domain_errors():
        user = await use_cases.create_user(session, command, actor_id=_actor_id(claims))
        await session.commit()
    await session.refresh(user)
    return user_to_response(user)


@router.get("/{user_id}", response_model=UserResponse, operation_id="getUser")
async def get_user(
    user_id: uuid.UUID,
    claims: _RequireManage,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Fetch a user with role grants and resolved permissions.

    Args:
        user_id: The internal user identifier.
        claims: The verified claims of the acting administrator.
        session: The unit-of-work session.

    Returns:
        The user.

    Raises:
        ProblemDetailError: 404 when the user does not exist.
    """
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise build_problem(404, "User not found", f"user {user_id} does not exist")
    return user_to_response(user)


@router.post("/{user_id}/roles", response_model=UserResponse, operation_id="assignRole")
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    claims: _RequireManage,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Grant a role to a user (idempotent).

    Args:
        user_id: The target user.
        body: The role to grant.
        claims: The verified claims of the acting administrator.
        session: The unit-of-work session.

    Returns:
        The updated user.
    """
    async with _domain_errors():
        user = await use_cases.assign_role(
            session, user_id=user_id, role=body.role, actor_id=_actor_id(claims)
        )
        await session.commit()
    await session.refresh(user)
    return user_to_response(user)


@router.delete("/{user_id}/roles/{role}", response_model=UserResponse, operation_id="revokeRole")
async def revoke_role(
    user_id: uuid.UUID,
    role: Role,
    claims: _RequireManage,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Revoke a role from a user (idempotent).

    Args:
        user_id: The target user.
        role: The role to revoke.
        claims: The verified claims of the acting administrator.
        session: The unit-of-work session.

    Returns:
        The updated user.
    """
    async with _domain_errors():
        user = await use_cases.revoke_role(
            session, user_id=user_id, role=role, actor_id=_actor_id(claims)
        )
        await session.commit()
    await session.refresh(user)
    return user_to_response(user)
