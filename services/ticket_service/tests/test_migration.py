"""Tests that the ticket-service migrations apply, seed, and roll back cleanly."""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ticket_service.application.commands import CreateTicketCommand
from ticket_service.application.errors import LegacyIdempotencyError
from ticket_service.application.use_cases import create_manual_ticket
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.migration_guards import RegulatoryDataPresentError
from ticket_service.infrastructure.reference_seed import SEED_ENTRIES
from ticket_service.infrastructure.registration import RegistrationNumberAllocator


def _make_config(db_path: Path) -> Config:
    """Build an Alembic config targeting a temporary SQLite database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A configured Alembic ``Config`` pointing at the service migrations.
    """
    service_root = Path(__file__).resolve().parents[1]
    config = Config(str(service_root / "alembic.ini"))
    config.set_main_option("script_location", str(service_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    return config


def _table_exists(db_path: Path, table: str) -> bool:
    """Return whether a table exists in a SQLite database.

    Args:
        db_path: Path to the SQLite database file.
        table: The table name to look for.

    Returns:
        ``True`` if the table exists.
    """
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchall()
    return rows == [(table,)]


def _count_rows(db_path: Path, table: str) -> int:
    """Return the number of rows in a table.

    Args:
        db_path: Path to the SQLite database file.
        table: The table to count.

    Returns:
        The row count.
    """
    with sqlite3.connect(db_path) as connection:
        (count,) = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(count)


def test_migrations_upgrade_create_schema_and_seed(tmp_path: Path) -> None:
    """Upgrading to head creates every table and seeds the draft dictionaries."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    for table in (
        "ticket",
        "ticket_applicant",
        "dictionary_entry",
        "registration_sequence",
        "ticket_comment",
        "outbox_event",
        "audit_log",
    ):
        assert _table_exists(db_path, table)
    # Statuses are seeded verbatim from docs/01 (seven values); the full seed set is larger.
    assert _count_rows(db_path, "dictionary_entry") > 7


def test_migrations_downgrade_removes_schema(tmp_path: Path) -> None:
    """Downgrading to base removes the schema without leaving tables behind."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    for table in (
        "ticket",
        "ticket_applicant",
        "dictionary_entry",
        "registration_sequence",
        "ticket_comment",
        "outbox_event",
        "audit_log",
    ):
        assert not _table_exists(db_path, table)


def test_runtime_catalog_matches_migration_snapshot(tmp_path: Path) -> None:
    """The runtime reference catalog matches the immutable migration seed (CRR-HIGH-001)."""
    db_path = tmp_path / "migration.db"
    command.upgrade(_make_config(db_path), "head")

    with sqlite3.connect(db_path) as connection:
        seeded = set(
            connection.execute(
                "SELECT dictionary_type, code FROM dictionary_entry WHERE is_active = 1"
            ).fetchall()
        )

    runtime = {(entry["dictionary_type"], entry["code"]) for entry in SEED_ENTRIES}
    assert seeded == runtime


def test_existing_tickets_are_marked_confidential_on_upgrade(tmp_path: Path) -> None:
    """A pre-existing ticket becomes confidential when 0005 applies (fail-closed; RR-HIGH-002)."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    # Upgrade to the revision just before the authorization-scope columns are added.
    command.upgrade(config, "0004")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO ticket (id, registration_number, received_at, registered_at, "
            "source_channel_code, subject, description, product_code, classifier_code, "
            "priority_code, current_status_code, current_stage_code, legal_hold, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)",
            (
                str(uuid.uuid4()),
                "AP-2026-000001",
                "2026-07-01T00:00:00+00:00",
                "2026-07-01T00:00:00+00:00",
                "EMAIL",
                "Historic sensitive appeal",
                "Body",
                "MICROLOAN",
                "RESTRUCTURING",
                "NORMAL",
                "NEW",
                "REGISTRATION",
            ),
        )
        connection.commit()

    # Apply the authorization-scope migration; unknown classification must fail closed.
    command.upgrade(config, "0005")
    with sqlite3.connect(db_path) as connection:
        (value,) = connection.execute("SELECT is_confidential FROM ticket").fetchone()
    assert value == 1


async def _retry_legacy_registration(
    db_path: Path, command_input: CreateTicketCommand, caller: TicketClaims
) -> None:
    """Retry a registration against the upgraded database, expecting a legacy-key refusal.

    Args:
        db_path: The upgraded SQLite database file.
        command_input: The registration command reusing the legacy idempotency key.
        caller: The authenticated caller.

    Raises:
        LegacyIdempotencyError: Always, because the stored row predates fingerprint scoping.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await create_manual_ticket(
                session, RegistrationNumberAllocator("AP"), command_input, caller
            )
    finally:
        await engine.dispose()


def test_legacy_key_retry_after_real_0004_to_head_upgrade_is_refused(
    tmp_path: Path,
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """A retry of a pre-scoping registration, migrated 0004->head, is a 409 with no new rows.

    Unlike the unit test that fabricates a head-schema legacy row, this exercises the real upgrade:
    a ticket is inserted under the 0004 schema (raw idempotency key, no fingerprint column yet), the
    database is upgraded to head (adding the scope and fingerprint columns with a NULL fingerprint),
    and a same-key retry is then refused (CR-BFF-R4-MEDIUM-003). The Alembic env runs its own event
    loop, so the async retry is driven via ``asyncio.run`` from this synchronous test.
    """
    db_path = tmp_path / "legacy-upgrade.db"
    config = _make_config(db_path)

    # Populate a legacy ticket under the 0004 schema: a raw idempotency key and no fingerprint.
    command.upgrade(config, "0004")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO ticket (id, registration_number, idempotency_key, received_at, "
            "registered_at, source_channel_code, subject, description, product_code, "
            "classifier_code, priority_code, current_status_code, current_stage_code, "
            "legal_hold, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)",
            (
                str(uuid.uuid4()),
                "AP-2026-000001",
                "legacy-key",
                "2026-07-01T00:00:00+00:00",
                "2026-07-01T00:00:00+00:00",
                "EMAIL",
                "Historic appeal",
                "Body",
                "MICROLOAN",
                "RESTRUCTURING",
                "NORMAL",
                "NEW",
                "REGISTRATION",
            ),
        )
        connection.commit()

    command.upgrade(config, "head")

    command_input = make_create_command(idempotency_key="legacy-key")
    with pytest.raises(LegacyIdempotencyError):
        asyncio.run(_retry_legacy_registration(db_path, command_input, make_caller()))

    # No duplicate ticket, event, or audit record resulted from the refused retry.
    assert _count_rows(db_path, "ticket") == 1
    assert _count_rows(db_path, "outbox_event") == 0
    assert _count_rows(db_path, "audit_log") == 0


def test_downgrade_is_blocked_when_protected_data_exists(tmp_path: Path) -> None:
    """A destructive downgrade aborts when regulatory/audit data is present (CR-BLOCKER-001)."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)
    command.upgrade(config, "head")

    # Seed one audit-log row (checked by the first downgrade to run, 0004).
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO audit_log (id, entity_type, entity_id, action) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), "ticket", str(uuid.uuid4()), "ticket.registered"),
        )
        connection.commit()

    with pytest.raises(RegulatoryDataPresentError):
        command.downgrade(config, "base")

    # The schema and the protected row survive the aborted rollback.
    assert _table_exists(db_path, "audit_log")
    assert _count_rows(db_path, "audit_log") == 1


def test_seed_downgrade_is_scoped_to_dictionaries(tmp_path: Path) -> None:
    """Reverting only the seed migration empties the dictionary but keeps the schema."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "0001")

    assert _table_exists(db_path, "dictionary_entry")
    assert _count_rows(db_path, "dictionary_entry") == 0
