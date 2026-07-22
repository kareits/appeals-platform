"""Shared pytest fixtures for ticket-service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from mfo_testing import create_asgi_client
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from ticket_service.application.commands import ApplicantInput, CreateTicketCommand
from ticket_service.config import Settings
from ticket_service.domain.enums import ApplicantType, DataSource, IdentifierType
from ticket_service.infrastructure.models import Base, DictionaryEntry
from ticket_service.infrastructure.reference_seed import SEED_ENTRIES
from ticket_service.main import create_app


async def _seed_dictionaries(engine: AsyncEngine) -> None:
    """Insert the reference dictionaries so use-case code validation passes in tests.

    Args:
        engine: The engine whose database receives the seed rows.
    """
    rows = [
        {
            "dictionary_type": entry["dictionary_type"],
            "code": entry["code"],
            "display_name_ru": entry["display_name_ru"],
            "display_name_kk": None,
            "sort_order": entry["sort_order"],
            "is_active": True,
        }
        for entry in SEED_ENTRIES
    ]
    async with engine.begin() as connection:
        await connection.execute(insert(DictionaryEntry), rows)


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
    await _seed_dictionaries(engine)
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
    await _seed_dictionaries(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def make_applicant() -> Callable[..., ApplicantInput]:
    """Return a builder for consumer applicant inputs.

    Returns:
        A callable that builds an :class:`ApplicantInput`, accepting field overrides.
    """

    def _build(**overrides: Any) -> ApplicantInput:
        """Build an applicant input with defaults and overrides.

        Args:
            **overrides: Fields to override.

        Returns:
            The applicant input.
        """
        defaults: dict[str, Any] = {
            "applicant_type": ApplicantType.CONSUMER,
            "data_source": DataSource.MANUAL,
            "full_name": "Иванов Иван",
            "identifier_type": IdentifierType.IIN,
            "identifier_value": "900101300123",
            "region_code": "ALA",
        }
        defaults.update(overrides)
        return ApplicantInput(**defaults)

    return _build


@pytest.fixture
def make_create_command(
    make_applicant: Callable[..., ApplicantInput],
) -> Callable[..., CreateTicketCommand]:
    """Return a builder for manual-registration commands.

    Args:
        make_applicant: The applicant-input builder fixture.

    Returns:
        A callable that builds a :class:`CreateTicketCommand`, accepting field overrides.
    """

    def _build(**overrides: Any) -> CreateTicketCommand:
        """Build a registration command with defaults and overrides.

        Args:
            **overrides: Fields to override.

        Returns:
            The registration command.
        """
        defaults: dict[str, Any] = {
            "received_at": datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
            "source_channel_code": "EMAIL",
            "subject": "Restructuring request",
            "description": "Full appeal text",
            "product_code": "MICROLOAN",
            "classifier_code": "RESTRUCTURING",
            "priority_code": "NORMAL",
            "applicant": make_applicant(),
        }
        defaults.update(overrides)
        return CreateTicketCommand(**defaults)

    return _build
