"""Tests that the ticket-service migrations apply, seed, and roll back cleanly."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from ticket_service.infrastructure.migration_guards import RegulatoryDataPresentError
from ticket_service.infrastructure.reference_seed import SEED_ENTRIES


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
