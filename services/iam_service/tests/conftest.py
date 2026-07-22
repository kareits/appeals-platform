"""Shared pytest fixtures for IAM-service tests.

Fixtures expose only library types (``AsyncClient``, ``async_sessionmaker``, ``Settings``, and
callables) so test modules never import a test-local class across files (the suite runs without a
``tests`` package; module basenames are unique per service).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from iam_service.config import Settings
from iam_service.domain.roles import Role
from iam_service.infrastructure.models import Base, User, UserRole
from iam_service.infrastructure.passwords import hash_password
from iam_service.infrastructure.tokens import TokenIssuer
from iam_service.main import create_app
from mfo_testing import create_asgi_client
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# A test secret long enough for HS256; never a real credential.
_TEST_JWT_SECRET = "test-secret-0123456789-abcdef-0123"
# Well-known password used by test-created users (mirrors the dev seed convention).
TEST_PASSWORD = "changeme-dev-01"


@dataclass
class _Harness:
    """Internal bundle of collaborators wired against one temporary database.

    Attributes:
        client: An ASGI client bound to the IAM application.
        session_factory: A session factory over the same database, for test setup.
        settings: The settings the application was built with.
    """

    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings


@pytest_asyncio.fixture
async def _harness(tmp_path: Path) -> AsyncIterator[_Harness]:
    """Wire an application, client, and session factory over one fresh SQLite database.

    The schema is created up front (no migrations) so readiness checks and queries succeed.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Yields:
        The wired internal harness.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'iam.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings = Settings(
        environment="test",
        database_url=database_url,
        dev_auth_enabled=True,
        jwt_secret=_TEST_JWT_SECRET,
    )
    app = create_app(settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with create_asgi_client(app) as client:
            yield _Harness(client=client, session_factory=factory, settings=settings)
    finally:
        await engine.dispose()


@pytest.fixture
def client(_harness: _Harness) -> AsyncClient:
    """Provide the ASGI client bound to the IAM application.

    Args:
        _harness: The internal harness.

    Returns:
        The HTTP client.
    """
    return _harness.client


@pytest.fixture
def session_factory(_harness: _Harness) -> async_sessionmaker[AsyncSession]:
    """Provide a session factory over the same database as the client, for test setup.

    Args:
        _harness: The internal harness.

    Returns:
        The session factory.
    """
    return _harness.session_factory


@pytest.fixture
def add_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[User]]:
    """Return an async helper that inserts a user with the given roles.

    Args:
        session_factory: The session factory over the test database.

    Returns:
        A callable that persists a user and returns it.
    """

    async def _add(
        username: str,
        *,
        roles: tuple[Role, ...] = (),
        password: str = TEST_PASSWORD,
        is_active: bool = True,
    ) -> User:
        """Persist a user with hashed credentials and role grants.

        Args:
            username: The login handle.
            roles: The roles to grant.
            password: The plaintext password to hash.
            is_active: Whether the account may authenticate.

        Returns:
            The persisted user.
        """
        async with session_factory() as session:
            user = User(
                username=username,
                full_name=username.title(),
                email=f"{username}@example.test",
                password_hash=hash_password(password),
                is_active=is_active,
            )
            for role in roles:
                user.roles.append(UserRole(role=role))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return _add


@pytest.fixture
def issuer(_harness: _Harness) -> TokenIssuer:
    """Provide a token issuer matching the application's signing configuration.

    Lets tests mint arbitrary (including deliberately malformed) tokens the running app will accept
    as validly signed.

    Args:
        _harness: The internal harness.

    Returns:
        A token issuer configured like the application's.
    """
    settings = _harness.settings
    return TokenIssuer(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_seconds=settings.jwt_ttl_seconds,
    )


@pytest.fixture
def login(client: AsyncClient) -> Callable[..., Awaitable[str]]:
    """Return an async helper that logs in and returns a bearer access token.

    Args:
        client: The HTTP client.

    Returns:
        A callable returning the access token string.
    """

    async def _login(username: str, password: str = TEST_PASSWORD) -> str:
        """Authenticate and return the access token.

        Args:
            username: The login handle.
            password: The plaintext password.

        Returns:
            The signed access token.
        """
        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        token: str = response.json()["accessToken"]
        return token

    return _login
