"""Shared pytest fixtures for ticket-service tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
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
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.models import Base, DictionaryEntry
from ticket_service.infrastructure.reference_seed import SEED_ENTRIES
from ticket_service.main import create_app

# Test signing material matching the ticket service's local defaults, so a minted token verifies.
_TEST_JWT_SECRET = "dev-insecure-secret-change-me-please"
_TEST_JWT_ISSUER = "mfo-iam"
_TEST_JWT_AUDIENCE = "mfo-appeals"
# A default caller identity used across tests unless a test overrides it.
DEFAULT_SUBJECT = uuid.UUID("018f9a3c-0000-7000-8000-0000000000aa")
# The full ticket permission set; a SUPERVISOR-like caller used by business-logic unit tests.
ALL_TICKET_PERMISSIONS = (
    "ticket:read",
    "ticket:create",
    "ticket:update",
    "ticket:classify",
    "ticket:comment",
    "ticket:decide",
    "ticket:close",
    "ticket:legal_hold",
)


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
        # Authenticate every request from this client as a default SUPERVISOR-like caller, so the
        # existing happy-path API tests exercise behavior beyond authentication. Auth-specific tests
        # use their own unauthenticated/limited clients.
        http_client.headers["Authorization"] = f"Bearer {_default_token()}"
        yield http_client


def _default_token() -> str:
    """Mint a default SUPERVISOR-like access token accepted by the ticket service.

    Returns:
        A signed token carrying organization-wide access and every ticket permission.
    """
    now = datetime.now(UTC)
    payload = {
        "iss": _TEST_JWT_ISSUER,
        "aud": _TEST_JWT_AUDIENCE,
        "sub": str(DEFAULT_SUBJECT),
        "username": "tester",
        "roles": ["SUPERVISOR"],
        "permissions": list(ALL_TICKET_PERMISSIONS),
        "teams": [],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


@pytest_asyncio.fixture
async def unauth_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Provide an ASGI client that sends no default Authorization header.

    Authorization tests attach their own per-request tokens (varying role, subject, and team) so a
    single database can be exercised as different callers.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Yields:
        An HTTP client bound to the ticket-service application with no default credentials.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'authz.db'}"
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
def make_caller() -> Callable[..., TicketClaims]:
    """Return a builder for authenticated-caller claims used by use-case unit tests.

    Defaults to a SUPERVISOR-like caller with organization-wide access and every ticket permission,
    so business-logic tests are not blocked by authorization; tests override roles/teams/permissions
    to exercise scope and permission behavior.

    Returns:
        A callable building :class:`TicketClaims`.
    """

    def _build(
        *,
        subject: uuid.UUID = DEFAULT_SUBJECT,
        roles: tuple[str, ...] = ("SUPERVISOR",),
        permissions: tuple[str, ...] = ALL_TICKET_PERMISSIONS,
        teams: tuple[str, ...] = (),
        username: str = "tester",
    ) -> TicketClaims:
        """Build caller claims with defaults and overrides.

        Args:
            subject: The caller's subject.
            roles: The caller's role-name claims.
            permissions: The caller's permission claims.
            teams: The caller's team identifier claims.
            username: The caller's username.

        Returns:
            The caller claims.
        """
        return TicketClaims(
            subject=subject,
            username=username,
            roles=tuple(roles),
            permissions=tuple(permissions),
            teams=tuple(teams),
        )

    return _build


@pytest.fixture
def make_token() -> Callable[..., str]:
    """Return a builder that mints a signed access token the ticket service will accept.

    Returns:
        A callable building a signed JWT with the given claims.
    """

    def _build(
        *,
        subject: uuid.UUID = DEFAULT_SUBJECT,
        roles: tuple[str, ...] = ("SUPERVISOR",),
        permissions: tuple[str, ...] = ALL_TICKET_PERMISSIONS,
        teams: tuple[str, ...] = (),
        username: str = "tester",
        secret: str = _TEST_JWT_SECRET,
        algorithm: str = "HS256",
        issuer: str = _TEST_JWT_ISSUER,
        audience: str = _TEST_JWT_AUDIENCE,
        expired: bool = False,
    ) -> str:
        """Mint a signed token with defaults and overrides.

        Args:
            subject: The subject claim.
            roles: The role-name claims.
            permissions: The permission claims.
            teams: The team identifier claims.
            username: The username claim.
            secret: The signing secret.
            algorithm: The signing algorithm.
            issuer: The ``iss`` claim.
            audience: The ``aud`` claim.
            expired: When true, issue an already-expired token.

        Returns:
            The encoded token.
        """
        now = datetime.now(UTC)
        exp = now - timedelta(minutes=1) if expired else now + timedelta(hours=1)
        payload = {
            "iss": issuer,
            "aud": audience,
            "sub": str(subject),
            "username": username,
            "roles": list(roles),
            "permissions": list(permissions),
            "teams": list(teams),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        return jwt.encode(payload, secret, algorithm=algorithm)

    return _build


@pytest.fixture
def auth_header(make_token: Callable[..., str]) -> dict[str, str]:
    """Return an Authorization header for a default SUPERVISOR-like caller.

    Args:
        make_token: The token builder fixture.

    Returns:
        A header mapping carrying a valid bearer token.
    """
    return {"Authorization": f"Bearer {make_token()}"}


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
