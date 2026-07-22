"""Tests for the user and role administration API.

Covers permission enforcement (iam:manage), user creation, idempotent role changes, and the
first-line read-only guarantee at the permission level (a first-line token cannot manage identity).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from iam_service.domain.roles import Role
from iam_service.infrastructure.models import User

_AddUser = Callable[..., Awaitable[User]]
_Login = Callable[..., Awaitable[str]]


def _auth(token: str) -> dict[str, str]:
    """Build an Authorization header for a bearer token.

    Args:
        token: The access token.

    Returns:
        A headers mapping carrying the bearer token.
    """
    return {"Authorization": f"Bearer {token}"}


async def test_admin_can_create_user(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """An administrator can create a user with initial roles; the response resolves permissions."""
    await add_user("admin", roles=(Role.ADMIN,))
    token = await login("admin")

    response = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={
            "username": "newbie",
            "fullName": "New Bie",
            "password": "initial-password",
            "roles": ["EMPLOYEE"],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == "newbie"
    assert body["roles"] == ["EMPLOYEE"]
    assert "ticket:read" in body["permissions"]


async def test_create_user_requires_authentication(client: AsyncClient) -> None:
    """Creating a user without a token is rejected with 401."""
    response = await client.post(
        "/api/v1/users",
        json={"username": "x", "fullName": "X", "password": "initial-password"},
    )
    assert response.status_code == 401


async def test_non_admin_cannot_create_user(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """A user lacking iam:manage is forbidden from creating users (403)."""
    await add_user("employee", roles=(Role.EMPLOYEE,))
    token = await login("employee")

    response = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={"username": "x", "fullName": "X", "password": "initial-password"},
    )
    assert response.status_code == 403


async def test_first_line_readonly_cannot_manage_identity(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """First-line read-only staff cannot perform identity management (403)."""
    await add_user("firstline", roles=(Role.FIRST_LINE_READONLY,))
    token = await login("firstline")

    response = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={"username": "x", "fullName": "X", "password": "initial-password"},
    )
    assert response.status_code == 403


async def test_duplicate_username_conflicts(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """Creating a user whose username is taken returns 409."""
    await add_user("admin", roles=(Role.ADMIN,))
    await add_user("taken", roles=(Role.EMPLOYEE,))
    token = await login("admin")

    response = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={"username": "taken", "fullName": "Dup", "password": "initial-password"},
    )
    assert response.status_code == 409


async def test_unknown_property_is_rejected(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """A request body with an unknown property is rejected with 422 (strict schema)."""
    await add_user("admin", roles=(Role.ADMIN,))
    token = await login("admin")

    response = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={
            "username": "y",
            "fullName": "Y",
            "password": "initial-password",
            "surprise": "unexpected",
        },
    )
    assert response.status_code == 422


async def test_assign_and_revoke_role_updates_permissions(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """Granting then revoking a role changes the user's resolved permissions."""
    admin = await add_user("admin", roles=(Role.ADMIN,))  # noqa: F841 - created for auth context
    target = await add_user("worker", roles=(Role.EMPLOYEE,))
    token = await login("admin")

    granted = await client.post(
        f"/api/v1/users/{target.id}/roles",
        headers=_auth(token),
        json={"role": "ANALYST"},
    )
    assert granted.status_code == 200, granted.text
    assert set(granted.json()["roles"]) == {"EMPLOYEE", "ANALYST"}
    assert "report:read" in granted.json()["permissions"]

    revoked = await client.request(
        "DELETE",
        f"/api/v1/users/{target.id}/roles/ANALYST",
        headers=_auth(token),
    )
    assert revoked.status_code == 200
    assert set(revoked.json()["roles"]) == {"EMPLOYEE"}
    assert "report:read" not in revoked.json()["permissions"]


async def test_assign_role_to_unknown_user_is_not_found(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """Assigning a role to a non-existent user returns 404."""
    await add_user("admin", roles=(Role.ADMIN,))
    token = await login("admin")

    response = await client.post(
        "/api/v1/users/00000000-0000-0000-0000-000000000000/roles",
        headers=_auth(token),
        json={"role": "EMPLOYEE"},
    )
    assert response.status_code == 404


async def test_get_user_returns_permissions(
    client: AsyncClient, add_user: _AddUser, login: _Login
) -> None:
    """Fetching a user returns roles and resolved permissions."""
    await add_user("admin", roles=(Role.ADMIN,))
    target = await add_user("someone", roles=(Role.OMBUDSMAN,))
    token = await login("admin")

    response = await client.get(f"/api/v1/users/{target.id}", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["OMBUDSMAN"]
    assert "ticket:decide" in body["permissions"]
