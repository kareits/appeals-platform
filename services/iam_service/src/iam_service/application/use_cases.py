"""IAM use cases: dev authentication and user/role administration.

Business logic lives here, not in route handlers (root ``CLAUDE.md``). Each use case stages its
writes and its audit entries into the caller's session; the API dependency commits the transaction
on success, so authentication logging, user creation, and role changes are atomic with their audit
records (docs/06 "role changes audited").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from iam_service.application.commands import CreateUserCommand
from iam_service.application.errors import (
    AuthenticationError,
    TeamNotFoundError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from iam_service.domain.permissions import resolve_permissions
from iam_service.domain.roles import Role
from iam_service.infrastructure import audit as audit_actions
from iam_service.infrastructure.audit import AuditRepository
from iam_service.infrastructure.models import User
from iam_service.infrastructure.passwords import hash_password_async, verify_password_async
from iam_service.infrastructure.repositories import TeamRepository, UserRepository
from iam_service.infrastructure.tokens import TokenIssuer


@dataclass(frozen=True)
class AuthResult:
    """Outcome of a successful authentication.

    Attributes:
        token: The signed access token.
        expires_in: Token lifetime in seconds.
        user: The authenticated user.
        roles: The user's role names.
        permissions: The permission strings resolved from those roles.
        teams: The identifiers of the teams the user belongs to.
    """

    token: str
    expires_in: int
    user: User
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    teams: tuple[str, ...]


def _sorted_roles(user: User) -> list[Role]:
    """Return the user's granted roles in a stable order.

    Args:
        user: The user whose grants to read.

    Returns:
        The granted roles sorted by their string value for deterministic claims.
    """
    return sorted((grant.role for grant in user.roles), key=lambda role: role.value)


async def authenticate_dev(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    issuer: TokenIssuer,
) -> AuthResult:
    """Authenticate a user with the dev/local credential scheme and issue a token.

    Verifies the password against the stored bcrypt hash, resolves permissions from the user's
    roles, issues a signed token, and records an authentication audit entry. Availability of the dev
    scheme (non-production) is enforced by the caller.

    Args:
        session: The active session (owns the audit write).
        username: The login handle.
        password: The plaintext password.
        issuer: The token issuer.

    Returns:
        The authentication result with the token and resolved claims.

    Raises:
        AuthenticationError: If the user is unknown, inactive, or the password is wrong.
    """
    users = UserRepository(session)
    user = await users.get_by_username(username)
    # Verify a hash even when the user is missing would be ideal to equalize timing; for a
    # non-production dev login the simple check is acceptable and the error message stays generic.
    if (
        user is None
        or not user.is_active
        or not await verify_password_async(password, user.password_hash)
    ):
        raise AuthenticationError("invalid username or password")

    roles = _sorted_roles(user)
    role_names = tuple(role.value for role in roles)
    permissions = tuple(sorted(permission.value for permission in resolve_permissions(set(roles))))
    # Team membership travels in the token so downstream services can enforce team/data scope from
    # self-contained claims without calling IAM. A user currently belongs to at most one team.
    teams = (str(user.team_id),) if user.team_id is not None else ()
    token, expires_in = issuer.issue(
        subject=user.id,
        username=user.username,
        roles=list(role_names),
        permissions=list(permissions),
        teams=list(teams),
    )
    AuditRepository(session).record(
        entity_id=user.id,
        action=audit_actions.ACTION_AUTHENTICATED,
        actor_id=user.id,
        details={"username": user.username},
    )
    return AuthResult(
        token=token,
        expires_in=expires_in,
        user=user,
        roles=role_names,
        permissions=permissions,
        teams=teams,
    )


async def create_user(
    session: AsyncSession,
    command: CreateUserCommand,
    *,
    actor_id: uuid.UUID | None,
) -> User:
    """Create a user with hashed credentials and initial role grants.

    Args:
        session: The active session (owns the writes and audit entry).
        command: The creation input.
        actor_id: The administrator performing the action, if known.

    Returns:
        The newly created user (flushed, with a generated identifier).

    Raises:
        UserAlreadyExistsError: If the username is already taken.
        TeamNotFoundError: If a referenced team does not exist.
    """
    users = UserRepository(session)
    if await users.username_exists(command.username):
        raise UserAlreadyExistsError(f"username {command.username!r} is already taken")
    if command.team_id is not None:
        team = await TeamRepository(session).get_by_id(command.team_id)
        if team is None:
            raise TeamNotFoundError(f"team {command.team_id} does not exist")

    user = User(
        username=command.username,
        full_name=command.full_name,
        email=command.email,
        password_hash=await hash_password_async(command.password),
        is_active=True,
        team_id=command.team_id,
    )
    for role in command.roles:
        UserRepository.grant_role(user, role)
    users.add(user)
    await session.flush()

    AuditRepository(session).record(
        entity_id=user.id,
        action=audit_actions.ACTION_USER_CREATED,
        actor_id=actor_id,
        details={
            "username": user.username,
            "roles": sorted(role.value for role in command.roles),
        },
    )
    return user


async def assign_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: Role,
    actor_id: uuid.UUID | None,
) -> User:
    """Grant a role to a user (idempotent), auditing only actual changes.

    Args:
        session: The active session.
        user_id: The target user.
        role: The role to grant.
        actor_id: The administrator performing the action, if known.

    Returns:
        The updated user.

    Raises:
        UserNotFoundError: If the user does not exist.
    """
    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(f"user {user_id} does not exist")
    if UserRepository.grant_role(user, role):
        AuditRepository(session).record(
            entity_id=user.id,
            action=audit_actions.ACTION_ROLE_ASSIGNED,
            actor_id=actor_id,
            details={"role": role.value},
        )
    return user


async def revoke_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: Role,
    actor_id: uuid.UUID | None,
) -> User:
    """Revoke a role from a user (idempotent), auditing only actual changes.

    Args:
        session: The active session.
        user_id: The target user.
        role: The role to revoke.
        actor_id: The administrator performing the action, if known.

    Returns:
        The updated user.

    Raises:
        UserNotFoundError: If the user does not exist.
    """
    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(f"user {user_id} does not exist")
    if UserRepository.revoke_role(user, role):
        AuditRepository(session).record(
            entity_id=user.id,
            action=audit_actions.ACTION_ROLE_REVOKED,
            actor_id=actor_id,
            details={"role": role.value},
        )
    return user
