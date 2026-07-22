"""Persistence for identity aggregates (users, role grants, teams).

Repositories stage changes into the caller's session; the API dependency owns the transaction
boundary and commits on success, so a failed request never persists a partial change (mirrors the
ticket service's unit-of-work convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iam_service.domain.roles import Role
from iam_service.infrastructure.models import Team, User, UserRole


class UserRepository:
    """Reads and writes user aggregates (including their role grants)."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active session whose transaction owns the changes.
        """
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        """Fetch a user by login handle.

        Args:
            username: The login handle to look up.

        Returns:
            The user, or ``None`` when no user has that handle.
        """
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by internal identifier.

        Args:
            user_id: The user's internal identifier.

        Returns:
            The user, or ``None`` when not found.
        """
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def username_exists(self, username: str) -> bool:
        """Return whether a user with the given handle exists.

        Args:
            username: The login handle to check.

        Returns:
            ``True`` when a user already has that handle.
        """
        result = await self._session.execute(
            select(User.id).where(User.username == username).limit(1)
        )
        return result.first() is not None

    def add(self, user: User) -> None:
        """Stage a new user for insertion.

        Args:
            user: The user to add.
        """
        self._session.add(user)

    @staticmethod
    def grant_role(user: User, role: Role) -> bool:
        """Grant a role to a user if not already granted.

        Args:
            user: The user to modify.
            role: The role to grant.

        Returns:
            ``True`` when the role was added; ``False`` when the user already held it.
        """
        if any(grant.role is role for grant in user.roles):
            return False
        user.roles.append(UserRole(role=role))
        return True

    @staticmethod
    def revoke_role(user: User, role: Role) -> bool:
        """Revoke a role from a user if present.

        Args:
            user: The user to modify.
            role: The role to revoke.

        Returns:
            ``True`` when the role was removed; ``False`` when the user did not hold it.
        """
        for grant in list(user.roles):
            if grant.role is role:
                user.roles.remove(grant)
                return True
        return False


class TeamRepository:
    """Reads team records."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active session.
        """
        self._session = session

    async def get_by_id(self, team_id: uuid.UUID) -> Team | None:
        """Fetch a team by internal identifier.

        Args:
            team_id: The team's internal identifier.

        Returns:
            The team, or ``None`` when not found.
        """
        result = await self._session.execute(select(Team).where(Team.id == team_id))
        return result.scalar_one_or_none()
