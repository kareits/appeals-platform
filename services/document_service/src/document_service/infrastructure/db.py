"""Database engine and session-factory construction for the document service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: The SQLAlchemy async database URL.

    Returns:
        A configured async engine.
    """
    return create_async_engine(database_url, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to an engine.

    Args:
        engine: The engine that produced sessions will use.

    Returns:
        An async session factory.
    """
    return async_sessionmaker(engine, expire_on_commit=False)
