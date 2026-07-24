"""PostgreSQL migration tests for the ticket service.

The SQLite migration tests run the real Alembic revision sequence but cannot expose
backend-specific DDL/data behavior of the ``0004 -> head`` upgrade (the authorization-scope backfill
in 0005 and the fingerprint column in 0006) on the production engine. These tests populate a legacy
ticket under the ``0004`` schema on a real PostgreSQL instance, upgrade to ``head``, and confirm a
same-key retry is safely refused with no new rows (CR-BFF-R5-MEDIUM-002). Because the run rebuilds
the ``public`` schema, it is destructive: it runs only when opted in against a disposable ``*_test``
database and fails closed on any other target (see :mod:`pg_test_safety`, CR-BFF-R6-MEDIUM-002).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pg_test_safety import destructive_tests_enabled, require_safe_test_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ticket_service.application.commands import CreateTicketCommand
from ticket_service.application.errors import LegacyIdempotencyError
from ticket_service.application.use_cases import create_manual_ticket
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.models import Base
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

pytestmark = pytest.mark.skipif(
    not destructive_tests_enabled(),
    reason=(
        "destructive PostgreSQL tests are opt-in; set ALLOW_DESTRUCTIVE_DATABASE_TESTS=1 and "
        "TICKET_TEST_DATABASE_URL to a disposable *_test database"
    ),
)


def _config(url: str) -> Config:
    """Build an Alembic config targeting the given database URL.

    Args:
        url: The async SQLAlchemy database URL.

    Returns:
        A configured Alembic ``Config`` pointing at the service migrations.
    """
    service_root = Path(__file__).resolve().parents[1]
    config = Config(str(service_root / "alembic.ini"))
    config.set_main_option("script_location", str(service_root / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


async def _reset_schema(url: str) -> None:
    """Drop only the ticket-owned tables so the test starts clean without touching the schema.

    Dropping just the mapped tables and Alembic's version table (rather than the whole ``public``
    schema) keeps the reset scoped to this service's objects, so an unrelated table sharing the
    disposable ``*_test`` database is never removed (CR-BFF-R6-LOW: smaller blast radius).

    Args:
        url: The async database URL.
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()


async def _scalar(url: str, sql: str) -> int:
    """Return a single integer scalar from a query.

    Args:
        url: The async database URL.
        sql: A query returning one integer.

    Returns:
        The scalar result.
    """
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return int((await connection.execute(text(sql))).scalar_one())
    finally:
        await engine.dispose()


async def _insert_legacy_ticket(url: str) -> str:
    """Insert a legacy ticket under the 0004 schema (raw key, no fingerprint column yet).

    Args:
        url: The async database URL.

    Returns:
        The registration number of the inserted legacy ticket.
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO ticket (id, registration_number, idempotency_key, received_at, "
                "registered_at, source_channel_code, subject, description, product_code, "
                "classifier_code, priority_code, current_status_code, current_stage_code, "
                "legal_hold, version) VALUES (:id, :rn, :key, :ts, :ts, 'EMAIL', "
                "'Historic appeal', 'Body', 'MICROLOAN', 'RESTRUCTURING', 'NORMAL', 'NEW', "
                "'REGISTRATION', false, 1)"
            ),
            {
                "id": uuid.uuid4(),
                "rn": "AP-2026-000001",
                "key": "legacy-key",
                "ts": datetime(2026, 7, 1, tzinfo=UTC),
            },
        )
    await engine.dispose()
    return "AP-2026-000001"


async def _retry_legacy(url: str, command_input: CreateTicketCommand, caller: TicketClaims) -> None:
    """Retry the registration against the upgraded database (expects a legacy-key refusal).

    Args:
        url: The async database URL.
        command_input: The registration command reusing the legacy idempotency key.
        caller: The authenticated caller.

    Raises:
        LegacyIdempotencyError: Always, because the stored row predates fingerprint scoping.
    """
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await create_manual_ticket(
                session, RegistrationNumberAllocator("AP"), command_input, caller
            )
    finally:
        await engine.dispose()


def _head_revision(config: Config) -> str | None:
    """Return the single head revision of the migration tree.

    Args:
        config: The Alembic config.

    Returns:
        The head revision identifier, or ``None`` when the tree is empty.
    """
    return ScriptDirectory.from_config(config).get_current_head()


async def _current_revision(url: str) -> str | None:
    """Return the revision the database is currently stamped at.

    Args:
        url: The async database URL.

    Returns:
        The current revision, or ``None`` when unstamped.
    """
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_revision()
            )
    finally:
        await engine.dispose()


def test_pg_legacy_key_retry_after_populated_0004_to_head_is_refused(
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """A populated 0004->head PostgreSQL upgrade refuses a legacy-key retry with no new rows."""
    url = require_safe_test_url()
    config = _config(url)

    asyncio.run(_reset_schema(url))
    command.upgrade(config, "0004")
    asyncio.run(_insert_legacy_ticket(url))
    command.upgrade(config, "head")

    # The database is really at head after the populated upgrade.
    assert asyncio.run(_current_revision(url)) == _head_revision(config)

    command_input = make_create_command(idempotency_key="legacy-key")
    with pytest.raises(LegacyIdempotencyError):
        asyncio.run(_retry_legacy(url, command_input, make_caller()))

    # No duplicate ticket, event, or audit record resulted, and the legacy row is intact.
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM ticket")) == 1
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM outbox_event")) == 0
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM audit_log")) == 0
    assert (
        asyncio.run(
            _scalar(url, "SELECT count(*) FROM ticket WHERE idempotency_key = 'legacy-key'")
        )
        == 1
    )
    # The backfilled scope column defaulted existing rows to confidential (fail-closed, 0005).
    assert (
        asyncio.run(_scalar(url, "SELECT count(*) FROM ticket WHERE is_confidential = true")) == 1
    )
