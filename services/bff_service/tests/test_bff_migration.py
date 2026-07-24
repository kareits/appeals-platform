"""Tests that the BFF baseline migration applies and rolls back cleanly.

The baseline creates no domain tables (the gateway is stateless in EP-1); the migration must still
apply and revert without error, and applying it must establish Alembic's bookkeeping so the
service's own schema is versioned.
"""

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


def test_baseline_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Upgrading establishes the Alembic version table and downgrading reverts cleanly."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    # The baseline creates no domain tables, but Alembic's bookkeeping table must be present.
    assert _table_exists(db_path, "alembic_version")

    command.downgrade(config, "base")
