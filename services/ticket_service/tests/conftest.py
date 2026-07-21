"""Shared pytest fixtures for ticket-service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient
from mfo_testing import create_asgi_client
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from ticket_service.config import Settings
from ticket_service.infrastructure.models import Base
from ticket_service.main import create_app


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Provide an ASGI client backed by a temporary SQLite database.

    The schema is created up front so readiness checks succeed without running migrations.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Yields:
        An HTTP client bound to the ticket-service application.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    app = create_app(Settings(environment="test", database_url=database_url))
    async with create_asgi_client(app) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide an async session factory over a temporary, schema-created SQLite database.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Yields:
        A session factory whose sessions target a fresh database with the full schema.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'session.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
