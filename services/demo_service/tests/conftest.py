"""Shared pytest fixtures for demo-service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from demo_service.config import Settings
from demo_service.infrastructure.models import Base
from demo_service.main import create_app
from httpx import AsyncClient
from mfo_testing import create_asgi_client
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Provide an ASGI client backed by a temporary SQLite database.

    The schema is created up front so readiness checks succeed without running migrations.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Yields:
        An HTTP client bound to the demo-service application.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    app = create_app(Settings(environment="test", database_url=database_url))
    async with create_asgi_client(app) as http_client:
        yield http_client
