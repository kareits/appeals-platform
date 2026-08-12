"""Shared pytest fixtures for document-service tests.

The reusable builders live in ``document_test_support`` so plain test modules can import them too;
this file only exposes them as fixtures. Every fixture wires a :class:`FakeScopeChecker` in place of
the Ticket-Service-backed appeal-scope adapter, so the document rules are exercised without a live
Ticket Service while the scope decision itself stays observable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from document_service.config import Settings
from document_service.infrastructure.local_storage import LocalFileStorage
from document_service.main import create_app
from document_test_support import FakeScopeChecker, build_settings, create_schema, mint_token
from httpx import AsyncClient
from mfo_testing import create_asgi_client
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def settings(tmp_path: Path) -> Settings:
    """Provide test settings with an initialized database schema.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        The settings instance whose database already has the document schema.
    """
    # Annotated explicitly: the shared helper module is imported through a mypy override, so its
    # return type arrives as Any.
    resolved: Settings = build_settings(tmp_path)
    await create_schema(resolved.database_url)
    return resolved


@pytest.fixture
def scope() -> FakeScopeChecker:
    """Provide a permissive appeal-scope stand-in that records every decision it is asked for.

    Returns:
        The fake scope checker used by the client fixtures.
    """
    checker: FakeScopeChecker = FakeScopeChecker()
    return checker


@pytest_asyncio.fixture
async def client(settings: Settings, scope: FakeScopeChecker) -> AsyncIterator[AsyncClient]:
    """Provide an ASGI client authenticated as a caller holding every document permission.

    Args:
        settings: The test settings fixture.
        scope: The appeal-scope stand-in.

    Yields:
        An HTTP client bound to the document-service application.
    """
    app = create_app(settings, scope_checker=scope)
    async with create_asgi_client(app) as http_client:
        http_client.headers["Authorization"] = f"Bearer {mint_token()}"
        yield http_client


@pytest_asyncio.fixture
async def small_limit_client(tmp_path: Path, scope: FakeScopeChecker) -> AsyncIterator[AsyncClient]:
    """Provide an authenticated client whose service accepts at most 1 KiB of file content.

    Args:
        tmp_path: Pytest-provided temporary directory.
        scope: The appeal-scope stand-in.

    Yields:
        An HTTP client bound to a size-limited document-service application.
    """
    resolved: Settings = build_settings(tmp_path, max_upload_bytes=1024)
    await create_schema(resolved.database_url)
    app = create_app(resolved, scope_checker=scope)
    async with create_asgi_client(app) as http_client:
        http_client.headers["Authorization"] = f"Bearer {mint_token()}"
        yield http_client


@pytest_asyncio.fixture
async def unauth_client(settings: Settings, scope: FakeScopeChecker) -> AsyncIterator[AsyncClient]:
    """Provide an ASGI client that sends no default Authorization header.

    Authentication and authorization tests attach their own per-request tokens.

    Args:
        settings: The test settings fixture.
        scope: The appeal-scope stand-in.

    Yields:
        An HTTP client bound to the document-service application with no default credentials.
    """
    app = create_app(settings, scope_checker=scope)
    async with create_asgi_client(app) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def session_factory(settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide an async session factory over the test database.

    Args:
        settings: The test settings fixture.

    Yields:
        A session factory whose sessions target the schema-created test database.
    """
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def storage(settings: Settings) -> LocalFileStorage:
    """Provide a local storage adapter rooted in the test storage directory.

    Args:
        settings: The test settings fixture.

    Returns:
        The storage adapter.
    """
    return LocalFileStorage(settings.storage_root)


@pytest.fixture
def make_token() -> Callable[..., str]:
    """Return a builder that mints a signed access token the document service will accept.

    Returns:
        A callable building a signed JWT with the given claims.
    """
    builder: Callable[..., str] = mint_token
    return builder
