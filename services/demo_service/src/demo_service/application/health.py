"""Application-level health checks for the demo service."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DatabaseHealthCheck:
    """Health check that verifies database connectivity.

    Satisfies the ``mfo_observability.HealthCheck`` protocol (a ``name`` attribute and an async
    call returning a boolean).
    """

    name = "database"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the check.

        Args:
            session_factory: Factory used to open a database session.
        """
        self._session_factory = session_factory

    async def __call__(self) -> bool:
        """Run a trivial query to confirm the database is reachable.

        Returns:
            ``True`` if the query succeeds.
        """
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
