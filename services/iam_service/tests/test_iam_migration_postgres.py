"""PostgreSQL migration tests for the IAM service.

The SQLite migration tests cannot expose backend-specific behavior such as the native ``iam_role``
enum type: revision 0002 must bind role values as the enum, not as ``VARCHAR`` (CR-IAM-BLOCKER-001).
These tests run the full migration lifecycle against a real PostgreSQL instance when
``IAM_TEST_DATABASE_URL`` points at one (an async ``postgresql+asyncpg://`` URL); they are skipped
otherwise so the default SQLite-only suite stays runnable without a database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from iam_service.infrastructure.migration_guards import ProtectedDataPresentError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_PG_URL = os.environ.get("IAM_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not _PG_URL,
    reason="IAM_TEST_DATABASE_URL is not set; PostgreSQL migration tests are skipped",
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
    """Drop and recreate the ``public`` schema so each test starts from a clean database.

    Args:
        url: The async database URL.
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
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
            result = await connection.execute(text(sql))
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _insert_audit_row(url: str) -> None:
    """Insert one audit row so the downgrade guard has non-seed data to protect.

    Args:
        url: The async database URL.
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO iam_audit_log (id, entity_type, entity_id, action) "
                "VALUES (:id, 'user', :eid, 'user.authenticated')"
            ),
            {"id": uuid.uuid4(), "eid": uuid.uuid4()},
        )
    await engine.dispose()


def test_pg_upgrade_creates_schema_and_seeds() -> None:
    """Upgrading to head on PostgreSQL creates the schema and seeds enum-typed role grants."""
    url = _PG_URL
    assert url is not None
    asyncio.run(_reset_schema(url))
    command.upgrade(_config(url), "head")

    assert asyncio.run(_scalar(url, "SELECT count(*) FROM iam_team")) == 2
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM iam_user")) == 7
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM iam_user_role")) == 7
    # The role column is the native enum; a distinct count confirms all seven labels inserted.
    assert asyncio.run(_scalar(url, "SELECT count(DISTINCT role) FROM iam_user_role")) == 7


def test_pg_downgrade_and_reupgrade_are_clean() -> None:
    """A full downgrade drops the schema and enum type; re-upgrading re-seeds successfully."""
    url = _PG_URL
    assert url is not None
    asyncio.run(_reset_schema(url))
    config = _config(url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    # The native enum type must be dropped so a re-upgrade can recreate it without conflict.
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM pg_type WHERE typname = 'iam_role'")) == 0

    command.upgrade(config, "head")
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM iam_user_role")) == 7


def test_pg_downgrade_blocked_when_protected_data_exists() -> None:
    """The guard aborts a destructive downgrade when non-seed audit data is present."""
    url = _PG_URL
    assert url is not None
    asyncio.run(_reset_schema(url))
    config = _config(url)
    command.upgrade(config, "head")
    asyncio.run(_insert_audit_row(url))

    with pytest.raises(ProtectedDataPresentError):
        command.downgrade(config, "base")

    # The schema and the protected row survive the aborted rollback.
    assert asyncio.run(_scalar(url, "SELECT count(*) FROM iam_audit_log")) == 1
