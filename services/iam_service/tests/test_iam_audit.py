"""Tests that identity actions are audited (docs/06 "role changes audited")."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from iam_service.domain.roles import Role
from iam_service.infrastructure import audit as audit_actions
from iam_service.infrastructure.models import AuditLog, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_AddUser = Callable[..., Awaitable[User]]
_Login = Callable[..., Awaitable[str]]


async def _actions_for(
    session_factory: async_sessionmaker[AsyncSession], action: str
) -> list[AuditLog]:
    """Return all audit entries with a given action code.

    Args:
        session_factory: The session factory over the test database.
        action: The audited action code to filter on.

    Returns:
        The matching audit-log rows.
    """
    async with session_factory() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.action == action))
        return list(result.scalars().all())


async def test_login_is_audited(
    session_factory: async_sessionmaker[AsyncSession],
    add_user: _AddUser,
    login: _Login,
) -> None:
    """A successful login writes an authentication audit entry for the user."""
    user = await add_user("employee", roles=(Role.EMPLOYEE,))
    await login("employee")

    entries = await _actions_for(session_factory, audit_actions.ACTION_AUTHENTICATED)
    assert [entry.entity_id for entry in entries] == [user.id]


async def test_role_assignment_is_audited(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    add_user: _AddUser,
    login: _Login,
) -> None:
    """Granting a role writes a role-assigned audit entry attributed to the administrator."""
    admin = await add_user("admin", roles=(Role.ADMIN,))
    target = await add_user("worker", roles=(Role.EMPLOYEE,))
    token = await login("admin")

    response = await client.post(
        f"/api/v1/users/{target.id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "ANALYST"},
    )
    assert response.status_code == 200

    entries = await _actions_for(session_factory, audit_actions.ACTION_ROLE_ASSIGNED)
    assert len(entries) == 1
    assert entries[0].entity_id == target.id
    assert entries[0].actor_id == admin.id
    assert entries[0].details == {"role": "ANALYST"}


async def test_role_reassignment_is_idempotent_and_not_double_audited(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    add_user: _AddUser,
    login: _Login,
) -> None:
    """Re-granting an already-held role makes no change and writes no new audit entry."""
    await add_user("admin", roles=(Role.ADMIN,))
    target = await add_user("worker", roles=(Role.EMPLOYEE,))
    token = await login("admin")

    headers = {"Authorization": f"Bearer {token}"}
    first = await client.post(
        f"/api/v1/users/{target.id}/roles", headers=headers, json={"role": "EMPLOYEE"}
    )
    assert first.status_code == 200

    entries = await _actions_for(session_factory, audit_actions.ACTION_ROLE_ASSIGNED)
    assert entries == []
