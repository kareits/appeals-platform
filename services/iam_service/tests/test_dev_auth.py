"""Tests for the dev/local authentication endpoints.

Covers the happy path (token + resolved claims), credential failures, and that dev login is disabled
in production (docs/06).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from httpx import AsyncClient
from iam_service.config import Settings
from iam_service.domain.roles import Role
from iam_service.infrastructure.models import Base, User, UserRole
from iam_service.infrastructure.passwords import hash_password
from iam_service.infrastructure.tokens import TokenIssuer
from iam_service.main import create_app
from mfo_testing import create_asgi_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_AddUser = Callable[..., Awaitable[User]]


async def test_login_returns_token_and_resolved_claims(
    client: AsyncClient, add_user: _AddUser
) -> None:
    """A valid login returns a token whose claims carry the user's roles and permissions."""
    await add_user("employee", roles=(Role.EMPLOYEE,))

    response = await client.post(
        "/api/v1/auth/login", json={"username": "employee", "password": "changeme-dev-01"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tokenType"] == "Bearer"
    assert body["username"] == "employee"
    assert body["roles"] == ["EMPLOYEE"]
    assert "ticket:read" in body["permissions"]
    assert body["accessToken"]


async def test_me_returns_claims_for_token(
    client: AsyncClient, add_user: _AddUser, login: Callable[..., Awaitable[str]]
) -> None:
    """GET /auth/me decodes the bearer token and returns the subject's claims."""
    await add_user("firstline", roles=(Role.FIRST_LINE_READONLY,))
    token = await login("firstline")

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "firstline"
    # First-line staff are read-only: only the ticket read permission is present.
    assert body["permissions"] == ["ticket:read"]


async def test_me_without_token_is_unauthorized(client: AsyncClient) -> None:
    """GET /auth/me without a bearer token is rejected with 401."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_token_with_unknown_role(client: AsyncClient, issuer: TokenIssuer) -> None:
    """A validly signed token carrying an unknown role fails closed with 401, not a 500."""
    token, _ = issuer.issue(
        subject=uuid.uuid4(),
        username="ghost",
        roles=["EMPLOYEE", "WIZARD"],  # WIZARD is not a known role
        permissions=["ticket:read"],
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_wrong_password_is_unauthorized(client: AsyncClient, add_user: _AddUser) -> None:
    """An incorrect password is rejected with 401."""
    await add_user("employee", roles=(Role.EMPLOYEE,))
    response = await client.post(
        "/api/v1/auth/login", json={"username": "employee", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_unknown_user_is_unauthorized(client: AsyncClient) -> None:
    """Logging in as an unknown user is rejected with 401."""
    response = await client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "changeme-dev-01"}
    )
    assert response.status_code == 401


async def test_inactive_user_is_unauthorized(client: AsyncClient, add_user: _AddUser) -> None:
    """An inactive account cannot authenticate."""
    await add_user("retired", roles=(Role.EMPLOYEE,), is_active=False)
    response = await client.post(
        "/api/v1/auth/login", json={"username": "retired", "password": "changeme-dev-01"}
    )
    assert response.status_code == 401


async def test_dev_login_disabled_in_production(tmp_path: Path) -> None:
    """In production the dev login endpoint is unavailable (403), before touching credentials."""
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(
            username="employee",
            full_name="Employee",
            password_hash=hash_password("changeme-dev-01"),
            is_active=True,
        )
        user.roles.append(UserRole(role=Role.EMPLOYEE))
        session.add(user)
        await session.commit()

    settings = Settings(
        environment="production",
        database_url=database_url,
        dev_auth_enabled=True,
        jwt_secret="prod-secret-0123456789-abcdefghij",
    )
    app = create_app(settings)
    try:
        async with create_asgi_client(app) as prod_client:
            response = await prod_client.post(
                "/api/v1/auth/login",
                json={"username": "employee", "password": "changeme-dev-01"},
            )
        assert response.status_code == 403
    finally:
        await engine.dispose()
