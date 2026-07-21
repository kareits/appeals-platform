"""Tests that the ticket-service migrations apply, seed, and roll back cleanly."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


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

    for table in ("ticket", "ticket_applicant", "dictionary_entry", "registration_sequence"):
        assert _table_exists(db_path, table)
    # Statuses are seeded verbatim from docs/01 (seven values); the full seed set is larger.
    assert _count_rows(db_path, "dictionary_entry") > 7


def test_migrations_downgrade_removes_schema(tmp_path: Path) -> None:
    """Downgrading to base removes the schema without leaving tables behind."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    for table in ("ticket", "ticket_applicant", "dictionary_entry", "registration_sequence"):
        assert not _table_exists(db_path, table)


def test_seed_downgrade_is_scoped_to_dictionaries(tmp_path: Path) -> None:
    """Reverting only the seed migration empties the dictionary but keeps the schema."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "0001")

    assert _table_exists(db_path, "dictionary_entry")
    assert _count_rows(db_path, "dictionary_entry") == 0
