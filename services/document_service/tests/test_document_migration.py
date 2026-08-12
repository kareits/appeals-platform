"""Tests that the document-service migrations apply and roll back safely."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from document_service.infrastructure.migration_guards import StoredDataPresentError


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


def _insert_document(db_path: Path) -> None:
    """Insert one document row directly, bypassing the application.

    Args:
        db_path: Path to the migrated SQLite database file.
    """
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO document (id, original_filename, storage_backend, storage_key, "
            "content_type, size_bytes, version, status, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                "evidence.pdf",
                "local",
                "2026/08/0123456789abcdef0123456789abcdef",
                "application/pdf",
                12,
                1,
                "AVAILABLE",
                str(uuid.uuid4()),
                "2026-08-11T00:00:00+00:00",
            ),
        )
        connection.commit()


def test_upgrade_creates_the_document_schema(tmp_path: Path) -> None:
    """Upgrading to head creates the document table and its indexes."""
    db_path = tmp_path / "migration.db"

    command.upgrade(_make_config(db_path), "head")

    assert _table_exists(db_path, "document")
    with sqlite3.connect(db_path) as connection:
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='document'"
            ).fetchall()
        }
    assert {
        "ix_document_ticket_id_created_at",
        "ix_document_message_id",
        "ix_document_status",
    } <= indexes


def test_downgrade_removes_an_empty_schema(tmp_path: Path) -> None:
    """Rolling back an empty database drops the table cleanly."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert not _table_exists(db_path, "document")


def test_downgrade_is_blocked_when_documents_exist(tmp_path: Path) -> None:
    """A rollback that would orphan stored files aborts and leaves the metadata intact."""
    db_path = tmp_path / "migration.db"
    config = _make_config(db_path)
    command.upgrade(config, "head")
    _insert_document(db_path)

    with pytest.raises(StoredDataPresentError):
        command.downgrade(config, "base")

    assert _table_exists(db_path, "document")
    with sqlite3.connect(db_path) as connection:
        (count,) = connection.execute("SELECT COUNT(*) FROM document").fetchone()
    assert count == 1


def test_storage_key_is_unique(tmp_path: Path) -> None:
    """The schema refuses two documents sharing a storage key, so bytes cannot be overwritten."""
    db_path = tmp_path / "migration.db"
    command.upgrade(_make_config(db_path), "head")
    _insert_document(db_path)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_document(db_path)


def test_downgrade_does_not_touch_stored_files(tmp_path: Path) -> None:
    """Rolling back the schema never deletes objects from the storage volume."""
    db_path = tmp_path / "migration.db"
    storage_root = tmp_path / "storage" / "2026" / "08"
    storage_root.mkdir(parents=True)
    stored = storage_root / "0123456789abcdef0123456789abcdef"
    stored.write_bytes(b"evidence")
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert stored.read_bytes() == b"evidence"
