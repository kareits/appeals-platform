"""Tests that the IAM-service migrations apply, seed, and roll back safely."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from iam_service.infrastructure.migration_guards import ProtectedDataPresentError
from iam_service.infrastructure.passwords import verify_password

_TABLES = ("iam_team", "iam_user", "iam_user_role", "iam_audit_log")
# The dev seed password embedded (as a bcrypt hash) in migration 0002.
_SEED_PASSWORD = "changeme-dev-01"


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
    """Upgrading to head creates every table and seeds teams, users, and role grants."""
    db_path = tmp_path / "migration.db"
    command.upgrade(_make_config(db_path), "head")

    for table in _TABLES:
        assert _table_exists(db_path, table)
    assert _count_rows(db_path, "iam_team") == 2
    assert _count_rows(db_path, "iam_user") == 7
    assert _count_rows(db_path, "iam_user_role") == 7


def test_seeded_user_password_hash_verifies(tmp_path: Path) -> None:
    """A seeded user's stored bcrypt hash verifies against the documented dev password."""
    db_path = tmp_path / "migration.db"
    command.upgrade(_make_config(db_path), "head")

    with sqlite3.connect(db_path) as connection:
        (password_hash,) = connection.execute(
            "SELECT password_hash FROM iam_user WHERE username = ?", ("firstline",)
        ).fetchone()
    assert verify_password(_SEED_PASSWORD, password_hash)


def test_migrations_downgrade_removes_schema(tmp_path: Path) -> None:
    """Downgrading to base removes the schema once the seed rows are gone."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    for table in _TABLES:
        assert not _table_exists(db_path, table)


def test_seed_downgrade_is_scoped_to_seeded_rows(tmp_path: Path) -> None:
    """Reverting only the seed migration empties users/teams but keeps the schema."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "0001")

    assert _table_exists(db_path, "iam_user")
    assert _count_rows(db_path, "iam_user") == 0
    assert _count_rows(db_path, "iam_team") == 0


def test_downgrade_is_blocked_when_protected_data_exists(tmp_path: Path) -> None:
    """A destructive downgrade aborts when non-seed identity/audit data is present."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)
    command.upgrade(config, "head")

    # An audit row is not removed by the scoped seed downgrade, so the 0001 guard must trip.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO iam_audit_log (id, entity_type, entity_id, action) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), "user", str(uuid.uuid4()), "user.authenticated"),
        )
        connection.commit()

    with pytest.raises(ProtectedDataPresentError):
        command.downgrade(config, "base")

    assert _table_exists(db_path, "iam_audit_log")
    assert _count_rows(db_path, "iam_audit_log") == 1
