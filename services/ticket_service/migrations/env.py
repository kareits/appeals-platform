"""Alembic migration environment for the ticket service.

Resolves the database URL from the Alembic config (when provided by tests) or the application
settings, and runs migrations against an async engine.
"""

from __future__ import annotations

import asyncio
from typing import Any

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from ticket_service.config import get_settings
from ticket_service.infrastructure.models import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the database URL for migrations.

    Returns:
        The URL from the Alembic config when set, otherwise the application settings value.
    """
    return config.get_main_option("sqlalchemy.url") or get_settings().resolved_database_url()


def run_migrations_offline() -> None:
    """Run migrations in offline mode, emitting SQL without a live connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Any) -> None:
    """Configure the context with a live connection and run migrations.

    Args:
        connection: The active database connection.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in online mode using an async engine."""
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
